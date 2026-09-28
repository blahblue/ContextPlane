"""Identity- and version-aware cache for context candidate resolution."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

from contextplane.auth import Principal
from contextplane.policy import PolicyRule
from contextplane.resolver import ContextResolutionRequest, ContextResolutionResult


@dataclass(frozen=True)
class _CacheEntry:
    """One bounded in-memory cache entry."""

    value: ContextResolutionResult
    expires_at: datetime


def _canonical_policy_rule(rule: PolicyRule) -> dict[str, object]:
    """Normalize policy rule ordering for a deterministic fingerprint."""
    return {
        "rule_id": rule.rule_id,
        "tenant_id": rule.tenant_id,
        "authority_level": rule.authority_level.value,
        "effect": rule.effect.value,
        "target_domains": (
            None
            if rule.target_domains is None
            else sorted(domain.value for domain in rule.target_domains)
        ),
        "allowed_keys": (
            None if rule.allowed_keys is None else sorted(rule.allowed_keys)
        ),
        "redact_keys": sorted(rule.redact_keys),
        "reason": rule.reason,
    }


def fingerprint_policy_rules(rules: tuple[PolicyRule, ...]) -> str:
    """Hash the complete configured policy state independently of rule ordering."""
    normalized = sorted(
        (_canonical_policy_rule(rule) for rule in rules),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )
    serialized = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_resolution_cache_key(
    *,
    principal: Principal,
    request: ContextResolutionRequest,
    context_revision: int,
    policy_fingerprint: str,
) -> str:
    """Build an opaque cache key covering identity, request, and version state."""
    scope = request.scope
    payload = {
        "principal": {
            "tenant_id": principal.tenant_id,
            "subject": principal.subject,
            "kind": principal.kind.value,
            "client_id": principal.client_id,
            "roles": sorted(principal.roles),
            "groups": sorted(principal.groups),
            "scopes": sorted(principal.scopes),
        },
        "scope": {
            "tenant_id": scope.tenant_id,
            "business_unit": scope.business_unit,
            "team": scope.team,
            "role": scope.role,
            "user_id": scope.user_id,
            "agent_id": scope.agent_id,
            "application": scope.application,
            "repository": scope.repository,
            "resource": scope.resource,
            "task": scope.task,
            "audience": scope.audience,
            "environment": scope.environment,
        },
        "domains": (
            None
            if request.domains is None
            else sorted(domain.value for domain in request.domains)
        ),
        "keys": None if request.keys is None else sorted(request.keys),
        "context_revision": context_revision,
        "policy_fingerprint": policy_fingerprint,
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class InMemoryResolutionCache:
    """Thread-safe bounded cache for candidate-resolution results."""

    def __init__(self, *, ttl_seconds: int = 60, max_entries: int = 1024) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be nonnegative")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        """Return successful lookup count."""
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        """Return failed/expired lookup count."""
        with self._lock:
            return self._misses

    @property
    def size(self) -> int:
        """Return current entry count."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Drop all process-local cached state and counters."""
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0

    def get(
        self,
        key: str,
        *,
        now: datetime,
    ) -> ContextResolutionResult | None:
        """Return a defensive copy when the entry remains temporally valid."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.expires_at <= now:
                if entry is not None:
                    self._entries.pop(key, None)
                self._misses += 1
                return None

            self._entries.move_to_end(key)
            self._hits += 1
            return entry.value.model_copy(deep=True)

    def put(
        self,
        key: str,
        value: ContextResolutionResult,
        *,
        now: datetime,
        next_transition: datetime | None,
    ) -> None:
        """Store a defensive copy until TTL or the next effective-time boundary."""
        if self._ttl_seconds == 0:
            return

        expires_at = now + timedelta(seconds=self._ttl_seconds)
        if next_transition is not None and next_transition < expires_at:
            expires_at = next_transition

        if expires_at <= now:
            return

        with self._lock:
            self._entries[key] = _CacheEntry(
                value=value.model_copy(deep=True),
                expires_at=expires_at,
            )
            self._entries.move_to_end(key)

            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

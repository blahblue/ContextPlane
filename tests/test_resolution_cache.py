from datetime import UTC, datetime, timedelta

from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import (
    InMemoryResolutionCache,
    build_resolution_cache_key,
    fingerprint_policy_rules,
)
from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextScope,
)
from contextplane.policy import PolicyEffect, PolicyRule
from contextplane.resolver import ContextResolutionRequest, ContextResolutionResult

NOW = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)


def principal(
    *,
    subject: str = "user-1",
    roles: frozenset[str] = frozenset({"developer"}),
) -> Principal:
    return Principal(
        tenant_id="tenant-a",
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="client-a",
        roles=roles,
        groups=frozenset({"platform"}),
        scopes=frozenset({"context.resolve"}),
    )


def request(*, task: str | None = None) -> ContextResolutionRequest:
    return ContextResolutionRequest(
        scope=ContextScope(
            tenant_id="tenant-a",
            user_id="user-1",
            application="client-a",
            task=task,
        ),
        domains=frozenset({ContextDomain.ENGINEERING}),
        keys=frozenset({"engineering.rule"}),
        as_of=NOW,
    )


def resolution() -> ContextResolutionResult:
    return ContextResolutionResult(
        tenant_id="tenant-a",
        as_of=NOW,
        candidates=(),
        explanations=(),
    )


def policy_rule(*, reason: str = "allow engineering") -> PolicyRule:
    return PolicyRule(
        rule_id="allow-engineering",
        tenant_id="tenant-a",
        authority_level=AuthorityLevel.POLICY,
        effect=PolicyEffect.ALLOW,
        target_domains=frozenset({ContextDomain.ENGINEERING}),
        reason=reason,
    )


def test_cache_key_is_deterministic_and_opaque() -> None:
    policy = fingerprint_policy_rules((policy_rule(),))

    first = build_resolution_cache_key(
        principal=principal(),
        request=request(task="build-api"),
        context_revision=7,
        policy_fingerprint=policy,
    )
    second = build_resolution_cache_key(
        principal=principal(),
        request=request(task="build-api"),
        context_revision=7,
        policy_fingerprint=policy,
    )

    assert first == second
    assert len(first) == 64
    assert "user-1" not in first
    assert "build-api" not in first


def test_cache_key_changes_with_principal_context_revision_and_policy() -> None:
    base_policy = fingerprint_policy_rules((policy_rule(),))
    base = build_resolution_cache_key(
        principal=principal(),
        request=request(),
        context_revision=1,
        policy_fingerprint=base_policy,
    )

    other_subject = build_resolution_cache_key(
        principal=principal(subject="user-2"),
        request=request(),
        context_revision=1,
        policy_fingerprint=base_policy,
    )
    other_revision = build_resolution_cache_key(
        principal=principal(),
        request=request(),
        context_revision=2,
        policy_fingerprint=base_policy,
    )
    other_policy = build_resolution_cache_key(
        principal=principal(),
        request=request(),
        context_revision=1,
        policy_fingerprint=fingerprint_policy_rules(
            (policy_rule(reason="updated policy"),)
        ),
    )

    assert len({base, other_subject, other_revision, other_policy}) == 4


def test_policy_fingerprint_is_independent_of_rule_order() -> None:
    second = PolicyRule(
        rule_id="allow-security",
        tenant_id="tenant-a",
        authority_level=AuthorityLevel.POLICY,
        effect=PolicyEffect.ALLOW,
        target_domains=frozenset({ContextDomain.SECURITY}),
        reason="allow security",
    )

    assert fingerprint_policy_rules((policy_rule(), second)) == fingerprint_policy_rules(
        (second, policy_rule())
    )


def test_cache_expires_at_next_context_transition() -> None:
    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=4)
    cache.put(
        "key",
        resolution(),
        now=NOW,
        next_transition=NOW + timedelta(seconds=5),
    )

    assert cache.get("key", now=NOW + timedelta(seconds=4)) is not None
    assert cache.get("key", now=NOW + timedelta(seconds=5)) is None
    assert cache.hits == 1
    assert cache.misses == 1


def test_cache_is_bounded_lru() -> None:
    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=2)

    cache.put("a", resolution(), now=NOW, next_transition=None)
    cache.put("b", resolution(), now=NOW, next_transition=None)
    assert cache.get("a", now=NOW) is not None

    cache.put("c", resolution(), now=NOW, next_transition=None)

    assert cache.get("b", now=NOW) is None
    assert cache.get("a", now=NOW) is not None
    assert cache.get("c", now=NOW) is not None
    assert cache.size == 2


def test_cache_returns_defensive_copy() -> None:
    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=2)
    original = resolution()
    cache.put("key", original, now=NOW, next_transition=None)

    loaded = cache.get("key", now=NOW)

    assert loaded is not None
    assert loaded is not original

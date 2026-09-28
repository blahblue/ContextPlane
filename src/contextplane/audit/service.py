"""Build deterministic secret-minimized resolution audit records."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from contextplane.audit.domain import (
    AuditConflictStepRef,
    AuditContextRef,
    AuditOutcome,
    ResolutionAuditCreate,
)
from contextplane.auth import Principal
from contextplane.context_registry.domain import ContextDomain
from contextplane.policy import PolicyDecision
from contextplane.resolver import EffectiveContextResult


def _policy_rule_ids(policy: PolicyDecision | None) -> tuple[str, ...]:
    """Flatten decisive/narrowing rule IDs without storing policy bodies."""
    if policy is None:
        return ()

    rule_ids = set(policy.narrowing_rule_ids)
    for decision in policy.domain_decisions:
        rule_ids.update(decision.decisive_rule_ids)
    return tuple(sorted(rule_ids))


def build_resolution_audit(
    *,
    resolution_id: UUID,
    principal: Principal,
    as_of: datetime,
    requested_domains: frozenset[ContextDomain],
    requested_keys: frozenset[str] | None,
    selector_dimensions: Iterable[str],
    policy: PolicyDecision | None,
    considered_record_ids: Iterable[UUID] = (),
    effective: EffectiveContextResult | None = None,
    outcome: AuditOutcome,
    error_code: str | None = None,
) -> ResolutionAuditCreate:
    """Create one audit record without raw prompt/context/request values."""
    returned_items: tuple[AuditContextRef, ...] = ()
    conflict_steps: tuple[AuditConflictStepRef, ...] = ()

    if effective is not None:
        returned_items = tuple(
            AuditContextRef(
                record_id=item.record_id,
                logical_id=item.logical_id,
                domain=item.domain,
                version=item.version,
            )
            for item in effective.effective
        )
        conflict_steps = tuple(
            AuditConflictStepRef(
                winner_record_id=step.winner_record_id,
                suppressed_record_id=step.suppressed_record_id,
            )
            for decision in effective.decisions
            for step in decision.steps
        )

    return ResolutionAuditCreate(
        resolution_id=resolution_id,
        tenant_id=principal.tenant_id,
        principal_kind=principal.kind,
        principal_subject=principal.subject,
        client_id=principal.client_id,
        as_of=as_of,
        requested_domains=tuple(sorted(requested_domains, key=lambda item: item.value)),
        requested_key_count=0 if requested_keys is None else len(requested_keys),
        selector_dimensions=tuple(sorted(set(selector_dimensions))),
        policy_decision=policy.decision if policy is not None else None,
        allowed_domains=(
            ()
            if policy is None
            else tuple(sorted(policy.allowed_domains, key=lambda item: item.value))
        ),
        denied_domains=(
            ()
            if policy is None
            else tuple(sorted(policy.denied_domains, key=lambda item: item.value))
        ),
        policy_rule_ids=_policy_rule_ids(policy),
        considered_record_ids=tuple(
            sorted(set(considered_record_ids), key=str)
        ),
        returned_items=returned_items,
        conflict_steps=conflict_steps,
        outcome=outcome,
        error_code=error_code,
    )

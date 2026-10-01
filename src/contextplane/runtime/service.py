"""Protocol-independent runtime orchestration for governed context resolution."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.audit import (
    AuditOutcome,
    build_resolution_audit,
    create_resolution_audit,
)
from contextplane.auth import Principal, PrincipalKind, principal_has_permission
from contextplane.cache import (
    InMemoryResolutionCache,
    build_resolution_cache_key,
    fingerprint_policy_rules,
)
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import ContextScope, SourceType
from contextplane.context_registry.state import get_context_state_snapshot
from contextplane.policy import (
    PolicyDecisionKind,
    PolicyEvaluationRequest,
    PolicyRule,
    PolicyTenantMismatchError,
    evaluate_policy,
)
from contextplane.resolver import (
    ContextPrecedenceConflictError,
    ContextResolutionRequest,
    ContextResolutionResult,
    apply_conflict_precedence,
    resolve_context_candidates,
)
from contextplane.runtime.domain import (
    ContextProvenance,
    EffectiveContextItem,
    ResolveContextRequest,
    ResolveContextResponse,
)


class RuntimeResolutionError(RuntimeError):
    """Base class for handled runtime failures with a durable correlation ID."""

    def __init__(self, message: str, *, resolution_id: UUID) -> None:
        super().__init__(message)
        self.resolution_id = resolution_id


class RuntimeAuthorizationError(RuntimeResolutionError):
    """Raised when an authenticated principal lacks runtime resolve permission."""


class RuntimePolicyConfigurationError(RuntimeResolutionError):
    """Raised after auditing invalid cross-tenant or malformed runtime policy."""


class RuntimeGovernanceConflictError(RuntimeResolutionError):
    """Raised after auditing an exact-precedence context governance conflict."""


def _scope_for_principal(
    principal: Principal,
    request: ResolveContextRequest,
) -> ContextScope:
    """Build resolver scope without trusting transport-supplied identity fields."""
    return ContextScope(
        tenant_id=principal.tenant_id,
        user_id=principal.subject if principal.kind is PrincipalKind.USER else None,
        agent_id=principal.subject if principal.kind is PrincipalKind.AGENT else None,
        application=principal.client_id,
        task=request.task,
        audience=request.audience,
        environment=request.environment,
        repository=request.repository,
        resource=request.resource,
    )


def _selector_dimensions(request: ResolveContextRequest) -> tuple[str, ...]:
    """Return selector names only; audit records never store selector values."""
    values = {
        "task": request.task,
        "audience": request.audience,
        "environment": request.environment,
        "repository": request.repository,
        "resource": request.resource,
    }
    return tuple(sorted(name for name, value in values.items() if value is not None))


def _apply_policy_filter(
    resolution: ContextResolutionResult,
    *,
    allowed_keys: frozenset[str] | None,
    redacted_keys: frozenset[str],
) -> ContextResolutionResult:
    """Remove policy-disallowed candidates before conflict precedence."""
    candidates = tuple(
        candidate
        for candidate in resolution.candidates
        if candidate.key not in redacted_keys
        and (allowed_keys is None or candidate.key in allowed_keys)
    )
    kept_ids = {candidate.record_id for candidate in candidates}
    explanations = tuple(
        explanation
        for explanation in resolution.explanations
        if explanation.record_id in kept_ids
    )
    return resolution.model_copy(
        update={
            "candidates": candidates,
            "explanations": explanations,
        }
    )


def _load_provenance(
    session: Session,
    *,
    tenant_id: str,
    record_ids: set[UUID],
) -> dict[UUID, ContextProvenance]:
    """Load safe provenance for effective records inside the authenticated tenant."""
    if not record_ids:
        return {}

    records = session.scalars(
        select(ContextItemRecord).where(
            ContextItemRecord.tenant_id == tenant_id,
            ContextItemRecord.id.in_(record_ids),
        )
    ).all()
    if len(records) != len(record_ids):
        raise RuntimeError("effective context provenance is incomplete")

    return {
        record.id: ContextProvenance(
            owner=record.owner,
            source_type=SourceType(record.source_type),
            source_identifier=record.source_identifier,
            checksum=record.checksum,
        )
        for record in records
    }


def resolve_context_runtime(
    *,
    request: ResolveContextRequest,
    principal: Principal,
    session: Session,
    rules: tuple[PolicyRule, ...],
    cache: InMemoryResolutionCache,
    as_of: datetime | None = None,
    resolution_id: UUID | None = None,
) -> ResolveContextResponse:
    """Execute the transport-neutral ContextPlane resolution pipeline."""
    evaluated_at = as_of or datetime.now(UTC)
    correlation_id = resolution_id or uuid4()

    if not principal_has_permission(principal, "context.resolve"):
        raise RuntimeAuthorizationError(
            "insufficient permission",
            resolution_id=correlation_id,
        )

    selector_dimensions = _selector_dimensions(request)

    try:
        policy = evaluate_policy(
            PolicyEvaluationRequest(
                tenant_id=principal.tenant_id,
                requested_domains=request.domains,
                requested_keys=request.keys,
            ),
            rules,
        )
    except PolicyTenantMismatchError:
        create_resolution_audit(
            session,
            build_resolution_audit(
                resolution_id=correlation_id,
                principal=principal,
                as_of=evaluated_at,
                requested_domains=request.domains,
                requested_keys=request.keys,
                selector_dimensions=selector_dimensions,
                policy=None,
                outcome=AuditOutcome.POLICY_ERROR,
                error_code="policy_configuration_invalid",
            ),
        )
        session.commit()
        raise RuntimePolicyConfigurationError(
            "policy configuration is invalid",
            resolution_id=correlation_id,
        ) from None

    if policy.decision is PolicyDecisionKind.DENY or not policy.allowed_domains:
        create_resolution_audit(
            session,
            build_resolution_audit(
                resolution_id=correlation_id,
                principal=principal,
                as_of=evaluated_at,
                requested_domains=request.domains,
                requested_keys=request.keys,
                selector_dimensions=selector_dimensions,
                policy=policy,
                outcome=AuditOutcome.DENIED,
            ),
        )
        session.commit()
        return ResolveContextResponse(
            resolution_id=correlation_id,
            tenant_id=principal.tenant_id,
            as_of=evaluated_at,
            policy=policy,
            context=(),
            candidate_explanations=(),
            conflict_decisions=(),
        )

    resolution_request = ContextResolutionRequest(
        scope=_scope_for_principal(principal, request),
        domains=policy.allowed_domains,
        keys=policy.allowed_keys,
        as_of=evaluated_at,
    )
    context_state = get_context_state_snapshot(
        session,
        tenant_id=principal.tenant_id,
        as_of=evaluated_at,
    )
    cache_key = build_resolution_cache_key(
        principal=principal,
        request=resolution_request,
        context_revision=context_state.revision,
        policy_fingerprint=fingerprint_policy_rules(rules),
    )
    resolution = cache.get(cache_key, now=evaluated_at)
    if resolution is None:
        resolution = resolve_context_candidates(session, resolution_request)
        cache.put(
            cache_key,
            resolution,
            now=evaluated_at,
            next_transition=context_state.next_transition,
        )
    else:
        resolution = resolution.model_copy(update={"as_of": evaluated_at})

    constrained = _apply_policy_filter(
        resolution,
        allowed_keys=policy.allowed_keys,
        redacted_keys=policy.redacted_keys,
    )
    considered_record_ids = tuple(
        candidate.record_id for candidate in constrained.candidates
    )

    try:
        effective = apply_conflict_precedence(constrained)
    except ContextPrecedenceConflictError:
        create_resolution_audit(
            session,
            build_resolution_audit(
                resolution_id=correlation_id,
                principal=principal,
                as_of=evaluated_at,
                requested_domains=request.domains,
                requested_keys=request.keys,
                selector_dimensions=selector_dimensions,
                policy=policy,
                considered_record_ids=considered_record_ids,
                outcome=AuditOutcome.CONFLICT,
                error_code="context_governance_conflict",
            ),
        )
        session.commit()
        raise RuntimeGovernanceConflictError(
            "context governance conflict",
            resolution_id=correlation_id,
        ) from None

    provenance = _load_provenance(
        session,
        tenant_id=principal.tenant_id,
        record_ids={candidate.record_id for candidate in effective.effective},
    )
    context = tuple(
        EffectiveContextItem(
            **candidate.model_dump(),
            provenance=provenance[candidate.record_id],
        )
        for candidate in effective.effective
    )

    winner_ids = {candidate.record_id for candidate in effective.effective}
    explanations = tuple(
        explanation
        for explanation in constrained.explanations
        if explanation.record_id in winner_ids
    )

    outcome = (
        AuditOutcome.NARROWED
        if policy.decision is PolicyDecisionKind.NARROW
        else AuditOutcome.ALLOWED
    )
    create_resolution_audit(
        session,
        build_resolution_audit(
            resolution_id=correlation_id,
            principal=principal,
            as_of=evaluated_at,
            requested_domains=request.domains,
            requested_keys=request.keys,
            selector_dimensions=selector_dimensions,
            policy=policy,
            considered_record_ids=considered_record_ids,
            effective=effective,
            outcome=outcome,
        ),
    )
    session.commit()

    return ResolveContextResponse(
        resolution_id=correlation_id,
        tenant_id=principal.tenant_id,
        as_of=effective.as_of,
        policy=policy,
        context=context,
        candidate_explanations=explanations,
        conflict_decisions=effective.decisions,
    )

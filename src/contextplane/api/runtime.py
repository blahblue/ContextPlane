"""Authenticated ContextPlane runtime resolution endpoint."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_database_session,
    get_policy_rules,
    get_resolution_cache,
)
from contextplane.api.domain import (
    ContextProvenance,
    EffectiveContextItem,
    ResolutionAuditResponse,
    ResolveContextRequest,
    ResolveContextResponse,
)
from contextplane.audit import (
    AuditConflictStepRef,
    AuditContextRef,
    AuditOutcome,
    build_resolution_audit,
    create_resolution_audit,
    get_resolution_audit_for_principal,
)
from contextplane.audit.db import ResolutionAuditRecord
from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import (
    InMemoryResolutionCache,
    build_resolution_cache_key,
    fingerprint_policy_rules,
)
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import ContextDomain, ContextScope, SourceType
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

router = APIRouter(prefix="/v1/context", tags=["context"])


def _scope_for_principal(
    principal: Principal,
    request: ResolveContextRequest,
) -> ContextScope:
    """Build resolver scope without trusting request-supplied identity fields."""
    return ContextScope(
        tenant_id=principal.tenant_id,
        user_id=principal.subject if principal.kind is PrincipalKind.USER else None,
        agent_id=principal.subject if principal.kind is PrincipalKind.AGENT else None,
        application=principal.client_id,
        task=request.task,
        audience=request.audience,
        environment=request.environment,
    )


def _selector_dimensions(request: ResolveContextRequest) -> tuple[str, ...]:
    """Return selector names only; audit records never store selector values."""
    values = {
        "task": request.task,
        "audience": request.audience,
        "environment": request.environment,
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


def _audit_to_response(record: ResolutionAuditRecord) -> ResolutionAuditResponse:
    """Convert a persisted audit row into the safe public lookup contract."""
    return ResolutionAuditResponse(
        resolution_id=record.resolution_id,
        tenant_id=record.tenant_id,
        principal_kind=PrincipalKind(record.principal_kind),
        as_of=record.as_of,
        requested_domains=tuple(
            ContextDomain(value) for value in record.requested_domains
        ),
        requested_key_count=record.requested_key_count,
        selector_dimensions=tuple(record.selector_dimensions),
        policy_decision=record.policy_decision,
        allowed_domains=tuple(
            ContextDomain(value) for value in record.allowed_domains
        ),
        denied_domains=tuple(
            ContextDomain(value) for value in record.denied_domains
        ),
        policy_rule_ids=tuple(record.policy_rule_ids),
        considered_record_ids=tuple(UUID(value) for value in record.considered_record_ids),
        returned_items=tuple(
            AuditContextRef.model_validate(item) for item in record.returned_items
        ),
        conflict_steps=tuple(
            AuditConflictStepRef.model_validate(item)
            for item in record.conflict_steps
        ),
        outcome=AuditOutcome(record.outcome),
        error_code=record.error_code,
        created_at=record.created_at,
    )


def _audit_headers(resolution_id: UUID) -> dict[str, str]:
    """Expose a correlation ID even for audited error responses."""
    return {"X-ContextPlane-Resolution-ID": str(resolution_id)}


@router.post("/resolve", response_model=ResolveContextResponse)
def resolve_context(
    request: ResolveContextRequest,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    rules: Annotated[tuple[PolicyRule, ...], Depends(get_policy_rules)],
    cache: Annotated[InMemoryResolutionCache, Depends(get_resolution_cache)],
) -> ResolveContextResponse:
    """Return policy-constrained effective organizational context."""
    as_of = datetime.now(UTC)
    resolution_id = uuid4()
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
                resolution_id=resolution_id,
                principal=principal,
                as_of=as_of,
                requested_domains=request.domains,
                requested_keys=request.keys,
                selector_dimensions=selector_dimensions,
                policy=None,
                outcome=AuditOutcome.POLICY_ERROR,
                error_code="policy_configuration_invalid",
            ),
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="policy configuration is invalid",
            headers=_audit_headers(resolution_id),
        ) from None

    if policy.decision is PolicyDecisionKind.DENY or not policy.allowed_domains:
        create_resolution_audit(
            session,
            build_resolution_audit(
                resolution_id=resolution_id,
                principal=principal,
                as_of=as_of,
                requested_domains=request.domains,
                requested_keys=request.keys,
                selector_dimensions=selector_dimensions,
                policy=policy,
                outcome=AuditOutcome.DENIED,
            ),
        )
        session.commit()
        return ResolveContextResponse(
            resolution_id=resolution_id,
            tenant_id=principal.tenant_id,
            as_of=as_of,
            policy=policy,
            context=(),
            candidate_explanations=(),
            conflict_decisions=(),
        )

    resolution_request = ContextResolutionRequest(
        scope=_scope_for_principal(principal, request),
        domains=policy.allowed_domains,
        keys=policy.allowed_keys,
        as_of=as_of,
    )
    context_state = get_context_state_snapshot(
        session,
        tenant_id=principal.tenant_id,
        as_of=as_of,
    )
    cache_key = build_resolution_cache_key(
        principal=principal,
        request=resolution_request,
        context_revision=context_state.revision,
        policy_fingerprint=fingerprint_policy_rules(rules),
    )
    resolution = cache.get(cache_key, now=as_of)
    if resolution is None:
        resolution = resolve_context_candidates(session, resolution_request)
        cache.put(
            cache_key,
            resolution,
            now=as_of,
            next_transition=context_state.next_transition,
        )
    else:
        resolution = resolution.model_copy(update={"as_of": as_of})

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
                resolution_id=resolution_id,
                principal=principal,
                as_of=as_of,
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="context governance conflict",
            headers=_audit_headers(resolution_id),
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
            resolution_id=resolution_id,
            principal=principal,
            as_of=as_of,
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
        resolution_id=resolution_id,
        tenant_id=principal.tenant_id,
        as_of=effective.as_of,
        policy=policy,
        context=context,
        candidate_explanations=explanations,
        conflict_decisions=effective.decisions,
    )


@router.get("/resolutions/{resolution_id}", response_model=ResolutionAuditResponse)
def get_resolution(
    resolution_id: UUID,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
) -> ResolutionAuditResponse:
    """Return one caller-owned audit record without raw context or token material."""
    record = get_resolution_audit_for_principal(
        session,
        principal=principal,
        resolution_id=resolution_id,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resolution not found",
        )

    return _audit_to_response(record)

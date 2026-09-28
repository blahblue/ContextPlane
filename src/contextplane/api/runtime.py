"""Authenticated ContextPlane runtime resolution endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_database_session,
    get_policy_rules,
)
from contextplane.api.domain import (
    ContextProvenance,
    EffectiveContextItem,
    ResolveContextRequest,
    ResolveContextResponse,
)
from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import ContextScope, SourceType
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
        repository=request.repository,
        resource=request.resource,
        task=request.task,
        audience=request.audience,
        environment=request.environment,
    )


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


@router.post("/resolve", response_model=ResolveContextResponse)
def resolve_context(
    request: ResolveContextRequest,
    principal: Principal = Depends(authenticate_principal),
    session: Session = Depends(get_database_session),
    rules: tuple[PolicyRule, ...] = Depends(get_policy_rules),
) -> ResolveContextResponse:
    """Return policy-constrained effective organizational context."""
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="policy configuration is invalid",
        ) from None

    if policy.decision is PolicyDecisionKind.DENY or not policy.allowed_domains:
        return ResolveContextResponse(
            tenant_id=principal.tenant_id,
            as_of=ContextResolutionRequest(
                scope=_scope_for_principal(principal, request),
                domains=frozenset(),
                keys=frozenset(),
            ).as_of,
            policy=policy,
            context=(),
            candidate_explanations=(),
            conflict_decisions=(),
        )

    resolution_request = ContextResolutionRequest(
        scope=_scope_for_principal(principal, request),
        domains=policy.allowed_domains,
        keys=policy.allowed_keys,
    )
    resolution = resolve_context_candidates(session, resolution_request)
    constrained = _apply_policy_filter(
        resolution,
        allowed_keys=policy.allowed_keys,
        redacted_keys=policy.redacted_keys,
    )

    try:
        effective = apply_conflict_precedence(constrained)
    except ContextPrecedenceConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="context governance conflict",
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

    return ResolveContextResponse(
        tenant_id=principal.tenant_id,
        as_of=effective.as_of,
        policy=policy,
        context=context,
        candidate_explanations=explanations,
        conflict_decisions=effective.decisions,
    )

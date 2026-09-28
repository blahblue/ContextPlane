"""FastAPI adapter for ContextPlane runtime resolution and audit lookup."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_database_session,
    get_policy_rules,
    get_resolution_cache,
)
from contextplane.api.domain import (
    ResolutionAuditResponse,
    ResolveContextRequest,
    ResolveContextResponse,
)
from contextplane.audit import (
    AuditConflictStepRef,
    AuditContextRef,
    AuditOutcome,
    get_resolution_audit_for_principal,
)
from contextplane.audit.db import ResolutionAuditRecord
from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import InMemoryResolutionCache
from contextplane.context_registry.domain import ContextDomain
from contextplane.policy import PolicyRule
from contextplane.runtime import (
    RuntimeGovernanceConflictError,
    RuntimePolicyConfigurationError,
    resolve_context_runtime,
)

router = APIRouter(prefix="/v1/context", tags=["context"])


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
    """Expose a correlation ID for handled runtime errors."""
    return {"X-ContextPlane-Resolution-ID": str(resolution_id)}


@router.post("/resolve", response_model=ResolveContextResponse)
def resolve_context(
    request: ResolveContextRequest,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    rules: Annotated[tuple[PolicyRule, ...], Depends(get_policy_rules)],
    cache: Annotated[InMemoryResolutionCache, Depends(get_resolution_cache)],
) -> ResolveContextResponse:
    """Adapt the protocol-independent resolver to HTTP semantics."""
    try:
        return resolve_context_runtime(
            request=request,
            principal=principal,
            session=session,
            rules=rules,
            cache=cache,
        )
    except RuntimePolicyConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="policy configuration is invalid",
            headers=_audit_headers(exc.resolution_id),
        ) from None
    except RuntimeGovernanceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="context governance conflict",
            headers=_audit_headers(exc.resolution_id),
        ) from None


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

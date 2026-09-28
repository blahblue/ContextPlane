"""HTTP-visible contracts for ContextPlane runtime and audit APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from contextplane.audit.domain import AuditConflictStepRef, AuditContextRef, AuditOutcome
from contextplane.auth import PrincipalKind
from contextplane.context_registry.domain import ContextDomain
from contextplane.runtime.domain import (
    ContextProvenance,
    EffectiveContextItem,
    ResolveContextRequest,
    ResolveContextResponse,
)

__all__ = [
    "ContextProvenance",
    "EffectiveContextItem",
    "ResolutionAuditResponse",
    "ResolveContextRequest",
    "ResolveContextResponse",
]


class ResolutionAuditResponse(BaseModel):
    """Safe caller-scoped view of one immutable resolution audit."""

    model_config = ConfigDict(extra="forbid")

    resolution_id: UUID
    tenant_id: str
    principal_kind: PrincipalKind
    as_of: datetime
    requested_domains: tuple[ContextDomain, ...]
    requested_key_count: int
    selector_dimensions: tuple[str, ...]
    policy_decision: str | None
    allowed_domains: tuple[ContextDomain, ...]
    denied_domains: tuple[ContextDomain, ...]
    policy_rule_ids: tuple[str, ...]
    considered_record_ids: tuple[UUID, ...]
    returned_items: tuple[AuditContextRef, ...]
    conflict_steps: tuple[AuditConflictStepRef, ...]
    outcome: AuditOutcome
    error_code: str | None
    created_at: datetime

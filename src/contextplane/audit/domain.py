"""Validated immutable audit models for context resolution."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
)

from contextplane.auth import PrincipalKind
from contextplane.context_registry.domain import ContextDomain
from contextplane.policy import PolicyDecisionKind

NonEmptyAuditString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
class AuditOutcome(StrEnum):
    """Runtime outcomes captured without raw context payloads."""

    ALLOWED = "allowed"
    NARROWED = "narrowed"
    DENIED = "denied"
    CONFLICT = "conflict"
    POLICY_ERROR = "policy_error"


class AuditContextRef(BaseModel):
    """Non-payload reference to one returned context version."""

    model_config = ConfigDict(extra="forbid")

    record_id: UUID
    logical_id: UUID
    domain: ContextDomain
    version: int


class AuditConflictStepRef(BaseModel):
    """Non-payload reference to one precedence suppression step."""

    model_config = ConfigDict(extra="forbid")

    winner_record_id: UUID
    suppressed_record_id: UUID


class ResolutionAuditCreate(BaseModel):
    """Complete append-only resolution audit record."""

    model_config = ConfigDict(extra="forbid")

    resolution_id: UUID
    tenant_id: NonEmptyAuditString
    principal_kind: PrincipalKind
    principal_subject: NonEmptyAuditString
    client_id: NonEmptyAuditString | None = None
    as_of: datetime

    requested_domains: tuple[ContextDomain, ...]
    requested_key_count: int = 0
    selector_dimensions: tuple[NonEmptyAuditString, ...] = ()

    policy_decision: PolicyDecisionKind | None = None
    allowed_domains: tuple[ContextDomain, ...] = ()
    denied_domains: tuple[ContextDomain, ...] = ()
    policy_rule_ids: tuple[NonEmptyAuditString, ...] = ()

    considered_record_ids: tuple[UUID, ...] = ()
    returned_items: tuple[AuditContextRef, ...] = ()
    conflict_steps: tuple[AuditConflictStepRef, ...] = ()

    outcome: AuditOutcome
    error_code: NonEmptyAuditString | None = None

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an unambiguous audit timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value

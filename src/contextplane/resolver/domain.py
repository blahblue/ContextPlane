"""Validated request and result models for context resolution."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contextplane.context_registry.domain import (
    AuthorityLevel,
    ContextDomain,
    ContextScope,
    OverridePolicy,
    SensitivityLevel,
)


class ContextResolutionRequest(BaseModel):
    """Context dimensions used to resolve applicable context candidates."""

    model_config = ConfigDict(extra="forbid")

    scope: ContextScope
    domains: frozenset[ContextDomain] | None = None
    keys: frozenset[str] | None = None
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an unambiguous evaluation time."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value


class CandidateExplanation(BaseModel):
    """Why one immutable context version matched the request."""

    model_config = ConfigDict(extra="forbid")

    logical_id: UUID
    record_id: UUID
    version: int
    matched_dimensions: tuple[str, ...]
    specificity: int
    reason: str


class ContextCandidate(BaseModel):
    """Compact resolver output before conflict precedence is applied."""

    model_config = ConfigDict(extra="forbid")

    logical_id: UUID
    record_id: UUID
    key: str
    value: dict[str, object] | None
    payload_ref: str | None
    domain: ContextDomain
    authority_level: AuthorityLevel
    sensitivity: SensitivityLevel
    override_policy: OverridePolicy
    version: int
    specificity: int
    matched_dimensions: tuple[str, ...]


class ContextResolutionResult(BaseModel):
    """Deterministic candidate set and explanation trace."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    as_of: datetime
    candidates: tuple[ContextCandidate, ...]
    explanations: tuple[CandidateExplanation, ...]


class ConflictStep(BaseModel):
    """One pairwise precedence decision in a key-level resolution."""

    model_config = ConfigDict(extra="forbid")

    winner_record_id: UUID
    suppressed_record_id: UUID
    reason: str


class ConflictDecision(BaseModel):
    """Auditable explanation for one key-level precedence decision."""

    model_config = ConfigDict(extra="forbid")

    key: str
    winner_record_id: UUID
    steps: tuple[ConflictStep, ...]


class EffectiveContextResult(BaseModel):
    """One effective context value per key after conflict precedence."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    as_of: datetime
    effective: tuple[ContextCandidate, ...]
    decisions: tuple[ConflictDecision, ...]

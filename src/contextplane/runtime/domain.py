"""Transport-neutral request and response contracts for governed context resolution."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from contextplane.context_registry.domain import (
    AuthorityLevel,
    ContextDomain,
    OverridePolicy,
    SensitivityLevel,
    SourceType,
)
from contextplane.policy.domain import PolicyDecision
from contextplane.resolver.domain import CandidateExplanation, ConflictDecision

NonEmptySelector = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class ResolveContextRequest(BaseModel):
    """Authenticated runtime request for governed context."""

    model_config = ConfigDict(extra="forbid")

    domains: frozenset[ContextDomain] = Field(min_length=1)
    keys: frozenset[NonEmptySelector] | None = None
    task: NonEmptySelector | None = None
    audience: NonEmptySelector | None = None
    environment: NonEmptySelector | None = None
    repository: NonEmptySelector | None = None
    resource: NonEmptySelector | None = None


class ContextProvenance(BaseModel):
    """Safe provenance metadata for one returned context version."""

    model_config = ConfigDict(extra="forbid")

    owner: str
    source_type: SourceType
    source_identifier: str
    checksum: str


class EffectiveContextItem(BaseModel):
    """One final context item returned to an authenticated client."""

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
    provenance: ContextProvenance


class ResolveContextResponse(BaseModel):
    """Policy-constrained effective context plus decision explanations."""

    model_config = ConfigDict(extra="forbid")

    resolution_id: UUID
    tenant_id: str
    as_of: datetime
    policy: PolicyDecision
    context: tuple[EffectiveContextItem, ...]
    candidate_explanations: tuple[CandidateExplanation, ...]
    conflict_decisions: tuple[ConflictDecision, ...]

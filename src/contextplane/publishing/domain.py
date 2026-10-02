"""Authenticated publishing contracts and persisted audit semantics."""

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from contextplane.auth import PrincipalKind
from contextplane.context_registry.domain import (
    AuthorityLevel,
    ContextDomain,
    OverridePolicy,
    SensitivityLevel,
)

NonEmptyPublicationString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
MAX_PUBLICATION_REQUEST_BYTES = 262_144


class PublicationAction(StrEnum):
    """Authenticated publication operations."""

    CREATE = "create"
    SUPERSEDE = "supersede"


class PublicationPermission(StrEnum):
    """Least-privilege permissions for assigning context authority."""

    PREFERENCE_SELF = "context.publish.preference.self"
    PREFERENCE = "context.publish.preference"
    RECOMMENDATION = "context.publish.recommendation"
    STANDARD = "context.publish.standard"
    POLICY = "context.publish.policy"
    MANDATORY_CONTROL = "context.publish.mandatory_control"


class PublicationApprovalPermission(StrEnum):
    """Explicit permissions for approving or activating high-authority context."""

    APPROVE_POLICY = "context.approve.policy"
    APPROVE_MANDATORY_CONTROL = "context.approve.mandatory_control"
    ACTIVATE_POLICY = "context.activate.policy"
    ACTIVATE_MANDATORY_CONTROL = "context.activate.mandatory_control"


class PublicationProposalState(StrEnum):
    """Derived lifecycle state for a high-authority proposal."""

    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"


class ApprovalEventType(StrEnum):
    """Immutable workflow event types."""

    APPROVE = "approve"
    ACTIVATE = "activate"


class ApprovalEventOutcome(StrEnum):
    """Immutable workflow event outcomes."""

    SUCCEEDED = "succeeded"
    DENIED = "denied"
    CONFLICT = "conflict"


class PublicationAuthorization(BaseModel):
    """Auditable authorization result for a publish attempt."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    subject: str
    principal_kind: PrincipalKind
    client_id: str | None
    action: PublicationAction
    authority_level: AuthorityLevel
    permission_used: PublicationPermission


class PublicationScopeInput(BaseModel):
    """Client-controlled applicability scope; tenant identity is server-derived."""

    model_config = ConfigDict(extra="forbid")

    business_unit: NonEmptyPublicationString | None = None
    team: NonEmptyPublicationString | None = None
    role: NonEmptyPublicationString | None = None
    user_id: NonEmptyPublicationString | None = None
    agent_id: NonEmptyPublicationString | None = None
    application: NonEmptyPublicationString | None = None
    repository: NonEmptyPublicationString | None = None
    resource: NonEmptyPublicationString | None = None
    task: NonEmptyPublicationString | None = None
    audience: NonEmptyPublicationString | None = None
    environment: NonEmptyPublicationString | None = None


class PublicationSourceInput(BaseModel):
    """Descriptive source reference for an API-authored context item."""

    model_config = ConfigDict(extra="forbid")

    identifier: NonEmptyPublicationString
    uri: NonEmptyPublicationString | None = None


class PublishContextRequest(BaseModel):
    """External authenticated write contract without tenant/publisher/checksum fields."""

    model_config = ConfigDict(extra="forbid")

    key: NonEmptyPublicationString
    value: dict[str, JsonValue] | None = None
    payload_ref: NonEmptyPublicationString | None = None
    domain: ContextDomain
    scope: PublicationScopeInput = PublicationScopeInput()
    owner: NonEmptyPublicationString
    source: PublicationSourceInput
    authority_level: AuthorityLevel
    effective_from: datetime
    effective_to: datetime | None = None
    sensitivity: SensitivityLevel
    override_policy: OverridePolicy

    @field_validator("effective_from", "effective_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("effective timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_payload_and_window(self) -> "PublishContextRequest":
        if (self.value is None) == (self.payload_ref is None):
            raise ValueError("exactly one of value or payload_ref must be provided")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")

        serialized = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(serialized) > MAX_PUBLICATION_REQUEST_BYTES:
            raise ValueError("publication request exceeds maximum serialized size")
        return self


class PublicationOutcome(StrEnum):
    """Persisted publication attempt result."""

    SUCCEEDED = "succeeded"
    DENIED = "denied"
    CONFLICT = "conflict"


class PublishContextResponse(BaseModel):
    """Idempotent safe response for an authenticated publication."""

    model_config = ConfigDict(extra="forbid")

    publication_id: UUID
    record_id: UUID
    logical_id: UUID
    version: int
    checksum: str
    action: PublicationAction
    authority_level: AuthorityLevel
    permission_used: PublicationPermission



class CreatePublicationProposalRequest(BaseModel):
    """Create a high-authority draft without activating it."""

    model_config = ConfigDict(extra="forbid")

    action: PublicationAction
    previous_id: UUID | None = None
    context: PublishContextRequest

    @model_validator(mode="after")
    def validate_action_shape(self) -> "CreatePublicationProposalRequest":
        if self.action is PublicationAction.CREATE and self.previous_id is not None:
            raise ValueError("create proposal cannot include previous_id")
        if self.action is PublicationAction.SUPERSEDE and self.previous_id is None:
            raise ValueError("supersede proposal requires previous_id")
        if self.context.authority_level not in {
            AuthorityLevel.POLICY,
            AuthorityLevel.MANDATORY_CONTROL,
        }:
            raise ValueError(
                "approval proposals are only for policy or mandatory_control"
            )
        return self


class PublicationProposalResponse(BaseModel):
    """Payload-minimized lifecycle response for a high-authority proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    state: PublicationProposalState
    action: PublicationAction
    authority_level: AuthorityLevel
    previous_id: UUID | None
    approval_event_id: UUID | None = None
    activation_event_id: UUID | None = None
    context_record_id: UUID | None = None
    logical_id: UUID | None = None
    version: int | None = None

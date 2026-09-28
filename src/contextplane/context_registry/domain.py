"""Validated domain models for organizational context."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class ContextDomain(StrEnum):
    """Initial governed context domains."""

    BRAND = "brand"
    PRESENTATION = "presentation"
    ENGINEERING = "engineering"
    SECURITY = "security"


class AuthorityLevel(StrEnum):
    """Semantic strength of a context item."""

    PREFERENCE = "preference"
    RECOMMENDATION = "recommendation"
    STANDARD = "standard"
    POLICY = "policy"
    MANDATORY_CONTROL = "mandatory_control"


class SensitivityLevel(StrEnum):
    """Data sensitivity classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class OverridePolicy(StrEnum):
    """Whether a lower scope can override this context item."""

    ALLOW = "allow"
    DENY = "deny"


class SourceType(StrEnum):
    """Supported source categories for provenance."""

    MANUAL = "manual"
    GIT = "git"
    SHAREPOINT = "sharepoint"
    GOOGLE_DRIVE = "google_drive"
    DATABRICKS = "databricks"
    FABRIC = "fabric"
    API = "api"


class ContextScope(BaseModel):
    """Identity and task dimensions controlling applicability."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyString
    business_unit: NonEmptyString | None = None
    team: NonEmptyString | None = None
    role: NonEmptyString | None = None
    user_id: NonEmptyString | None = None
    agent_id: NonEmptyString | None = None
    application: NonEmptyString | None = None
    repository: NonEmptyString | None = None
    resource: NonEmptyString | None = None
    task: NonEmptyString | None = None
    audience: NonEmptyString | None = None
    environment: NonEmptyString | None = None


class ContextSource(BaseModel):
    """Provenance pointer to an authoritative source."""

    model_config = ConfigDict(extra="forbid")

    type: SourceType
    identifier: NonEmptyString
    uri: NonEmptyString | None = None


class ContextItemCreate(BaseModel):
    """Validated input for a new context item."""

    model_config = ConfigDict(extra="forbid")

    key: NonEmptyString
    value: dict[str, JsonValue] | None = None
    payload_ref: NonEmptyString | None = None
    domain: ContextDomain
    scope: ContextScope
    owner: NonEmptyString
    source: ContextSource
    authority_level: AuthorityLevel
    effective_from: datetime
    effective_to: datetime | None = None
    sensitivity: SensitivityLevel
    override_policy: OverridePolicy
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("effective_from", "effective_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Require timezone-aware effective timestamps."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("effective timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_payload_and_window(self) -> Self:
        """Require one payload form and a non-inverted effective window."""
        if (self.value is None) == (self.payload_ref is None):
            raise ValueError("exactly one of value or payload_ref must be provided")

        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")

        return self

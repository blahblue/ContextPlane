"""Authorization model for authenticated context publishing."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from contextplane.auth import PrincipalKind
from contextplane.context_registry.domain import AuthorityLevel


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

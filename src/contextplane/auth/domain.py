"""Authenticated principal models shared across identity providers."""

from enum import StrEnum
from typing import Annotated, Protocol, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonEmptyIdentityString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class PrincipalKind(StrEnum):
    """Identity categories ContextPlane keeps distinct."""

    USER = "user"
    AGENT = "agent"
    SERVICE = "service"


class Principal(BaseModel):
    """Normalized authenticated identity used by policy and resolution layers."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyIdentityString
    subject: NonEmptyIdentityString
    kind: PrincipalKind
    client_id: NonEmptyIdentityString | None = None
    roles: frozenset[NonEmptyIdentityString] = frozenset()
    groups: frozenset[NonEmptyIdentityString] = frozenset()
    scopes: frozenset[NonEmptyIdentityString] = frozenset()

    @model_validator(mode="after")
    def require_client_identity_for_non_user(self) -> Self:
        """Agents and services require an explicit client/application identity."""
        if self.kind in {PrincipalKind.AGENT, PrincipalKind.SERVICE} and self.client_id is None:
            raise ValueError("agent and service principals require client_id")
        return self


class PrincipalValidator(Protocol):
    """Provider-neutral boundary for validating a bearer token."""

    def validate(self, token: str) -> Principal:
        """Validate a token and return a normalized principal."""
        ...


def principal_has_permission(principal: Principal, permission: str) -> bool:
    """Return whether delegated scopes or application roles grant a permission."""
    return permission in principal.scopes or permission in principal.roles

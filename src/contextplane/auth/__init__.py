"""Authentication and normalized identity primitives."""

from contextplane.auth.domain import Principal, PrincipalKind, PrincipalValidator
from contextplane.auth.entra import (
    EntraValidatorConfig,
    StaticKeyEntraValidator,
    principal_from_entra_claims,
)
from contextplane.auth.oidc import (
    AuthenticationError,
    OIDCValidatorConfig,
    StaticKeyOIDCValidator,
    principal_from_oidc_claims,
)

__all__ = [
    "AuthenticationError",
    "EntraValidatorConfig",
    "OIDCValidatorConfig",
    "Principal",
    "PrincipalKind",
    "PrincipalValidator",
    "StaticKeyOIDCValidator",
    "StaticKeyEntraValidator",
    "principal_from_oidc_claims",
    "principal_from_entra_claims",
]

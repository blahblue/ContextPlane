"""Authentication and normalized identity primitives."""

from contextplane.auth.domain import Principal, PrincipalKind
from contextplane.auth.oidc import (
    AuthenticationError,
    OIDCValidatorConfig,
    StaticKeyOIDCValidator,
    principal_from_oidc_claims,
)

__all__ = [
    "AuthenticationError",
    "OIDCValidatorConfig",
    "Principal",
    "PrincipalKind",
    "StaticKeyOIDCValidator",
    "principal_from_oidc_claims",
]

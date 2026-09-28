"""Authentication and normalized identity primitives."""

from contextplane.auth.domain import Principal, PrincipalKind, PrincipalValidator
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
    "PrincipalValidator",
    "StaticKeyOIDCValidator",
    "principal_from_oidc_claims",
]

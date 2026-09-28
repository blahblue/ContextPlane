"""Static-key OIDC validation and normalization into ContextPlane principals."""

from typing import Annotated, Any

import jwt
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from contextplane.auth.domain import Principal, PrincipalKind

NonEmptyOIDCString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]


class AuthenticationError(RuntimeError):
    """Generic authentication failure without token-validation detail leakage."""


class OIDCValidatorConfig(BaseModel):
    """Configuration for one trusted OIDC issuer and audience."""

    model_config = ConfigDict(extra="forbid")

    issuer: NonEmptyOIDCString
    audience: NonEmptyOIDCString
    public_key_pem: NonEmptyOIDCString
    clock_skew_seconds: int = Field(default=30, ge=0, le=300)


def _string_set_claim(
    claims: dict[str, Any],
    name: str,
) -> frozenset[str]:
    """Parse an optional array claim into a normalized immutable string set."""
    raw = claims.get(name)
    if raw is None:
        return frozenset()
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item.strip() for item in raw):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return frozenset(item.strip() for item in raw)


def _scope_claim(claims: dict[str, Any]) -> frozenset[str]:
    """Parse the standard space-delimited scope claim."""
    raw = claims.get("scope")
    if raw is None:
        return frozenset()
    if not isinstance(raw, str):
        raise ValueError("scope must be a space-delimited string")
    return frozenset(part for part in raw.split() if part)


def principal_from_oidc_claims(claims: dict[str, Any]) -> Principal:
    """Normalize validated generic OIDC claims into a ContextPlane principal."""
    raw_kind = claims.get("principal_type")
    raw_client_id = claims.get("client_id")

    if raw_client_id is not None and not isinstance(raw_client_id, str):
        raise ValueError("client_id must be a string")

    return Principal(
        tenant_id=claims.get("tenant_id"),
        subject=claims.get("sub"),
        kind=PrincipalKind(raw_kind),
        client_id=raw_client_id,
        roles=_string_set_claim(claims, "roles"),
        groups=_string_set_claim(claims, "groups"),
        scopes=_scope_claim(claims),
    )


class StaticKeyOIDCValidator:
    """Validate RS256 OIDC tokens against a pinned public key."""

    def __init__(self, config: OIDCValidatorConfig) -> None:
        self._config = config

    def validate(self, token: str) -> Principal:
        """Validate signature/standard claims and return a normalized principal."""
        try:
            claims = jwt.decode(
                token,
                self._config.public_key_pem,
                algorithms=["RS256"],
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.clock_skew_seconds,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                },
            )
            return principal_from_oidc_claims(claims)
        except (jwt.PyJWTError, ValidationError, ValueError, TypeError) as exc:
            raise AuthenticationError("token validation failed") from None

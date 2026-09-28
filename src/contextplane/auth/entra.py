"""Microsoft Entra access-token validation and principal normalization."""

from typing import Annotated, Any

import jwt
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from contextplane.auth.domain import Principal, PrincipalKind
from contextplane.auth.oidc import AuthenticationError

NonEmptyEntraString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]


class EntraValidatorConfig(BaseModel):
    """Trusted Microsoft Entra tenant/API configuration for the reference adapter."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyEntraString
    issuer: NonEmptyEntraString
    audience: NonEmptyEntraString
    public_key_pem: NonEmptyEntraString
    clock_skew_seconds: int = Field(default=30, ge=0, le=300)


def _required_string(claims: dict[str, Any], name: str) -> str:
    """Read one required non-empty string claim."""
    raw = claims.get(name)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return raw.strip()


def _optional_string(claims: dict[str, Any], name: str) -> str | None:
    """Read one optional non-empty string claim."""
    raw = claims.get(name)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be a non-empty string when present")
    return raw.strip()


def _string_array(claims: dict[str, Any], name: str) -> frozenset[str]:
    """Parse an optional Entra array claim into a normalized string set."""
    raw = claims.get(name)
    if raw is None:
        return frozenset()
    if not isinstance(raw, list) or any(
        not isinstance(item, str) or not item.strip() for item in raw
    ):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return frozenset(item.strip() for item in raw)


def _scopes(claims: dict[str, Any]) -> frozenset[str]:
    """Parse Microsoft Entra's space-delimited delegated permission claim."""
    raw = claims.get("scp")
    if raw is None:
        return frozenset()
    if not isinstance(raw, str):
        raise ValueError("scp must be a space-delimited string")
    return frozenset(part for part in raw.split() if part)


def _reject_group_overage(claims: dict[str, Any]) -> None:
    """Fail closed until Graph-backed group overage resolution is implemented."""
    if claims.get("hasgroups") is True:
        raise ValueError("group overage requires external membership resolution")

    claim_names = claims.get("_claim_names")
    if claim_names is None:
        return
    if not isinstance(claim_names, dict):
        raise ValueError("_claim_names must be an object")
    if "groups" in claim_names:
        raise ValueError("group overage requires external membership resolution")


def _client_id(claims: dict[str, Any]) -> str:
    """Resolve the calling application ID across Entra token versions."""
    azp = _optional_string(claims, "azp")
    appid = _optional_string(claims, "appid")

    if azp is not None and appid is not None and azp != appid:
        raise ValueError("azp and appid disagree")

    client_id = azp or appid
    if client_id is None:
        raise ValueError("Entra access token must include azp or appid")
    return client_id


def principal_from_entra_claims(
    claims: dict[str, Any],
    *,
    expected_tenant_id: str,
) -> Principal:
    """Map already-validated Entra access-token claims into a ContextPlane principal."""
    tenant_id = _required_string(claims, "tid")
    if tenant_id != expected_tenant_id:
        raise ValueError("token tenant does not match configured tenant")

    subject = _required_string(claims, "oid")
    client_id = _client_id(claims)
    scopes = _scopes(claims)
    roles = _string_array(claims, "roles")
    groups = _string_array(claims, "groups")
    _reject_group_overage(claims)

    idtyp = _optional_string(claims, "idtyp")
    subject_function = _optional_string(claims, "xms_sub_fct")
    actor_function = _optional_string(claims, "xms_act_fct")

    if idtyp == "app":
        kind = (
            PrincipalKind.AGENT
            if subject_function == "11" or actor_function == "11"
            else PrincipalKind.SERVICE
        )
    elif idtyp in {None, "user"} and scopes:
        # idtyp is optional on user access tokens unless the API requests it.
        kind = PrincipalKind.USER
    elif idtyp == "user":
        kind = PrincipalKind.USER
    else:
        raise ValueError("unable to determine Entra principal type safely")

    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=kind,
        client_id=client_id,
        roles=roles,
        groups=groups,
        scopes=scopes,
    )


class StaticKeyEntraValidator:
    """Validate a single-tenant Entra JWT using a pinned RSA public key."""

    def __init__(self, config: EntraValidatorConfig) -> None:
        self._config = config

    def validate(self, token: str) -> Principal:
        """Validate cryptographic/standard claims, tenant, and Entra identity claims."""
        try:
            claims = jwt.decode(
                token,
                self._config.public_key_pem,
                algorithms=["RS256"],
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.clock_skew_seconds,
                options={
                    "require": ["exp", "iat", "iss", "aud"],
                },
            )
            return principal_from_entra_claims(
                claims,
                expected_tenant_id=self._config.tenant_id,
            )
        except (jwt.PyJWTError, ValidationError, ValueError, TypeError):
            raise AuthenticationError("token validation failed") from None

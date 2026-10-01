import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from contextplane.auth import EntraValidatorConfig, PrincipalKind, StaticKeyEntraValidator
from contextplane.mcp import ContextPlaneEntraTokenVerifier

TENANT = "11111111-2222-3333-4444-555555555555"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
AUDIENCE = "api://contextplane"


def keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "tid": TENANT,
        "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azp": "99999999-8888-7777-6666-555555555555",
        "scp": "context.resolve",
    }
    payload.update(overrides)
    return payload


def verifier(public_key: str) -> ContextPlaneEntraTokenVerifier:
    return ContextPlaneEntraTokenVerifier(
        StaticKeyEntraValidator(
            EntraValidatorConfig(
                tenant_id=TENANT,
                issuer=ISSUER,
                audience=AUDIENCE,
                public_key_pem=public_key,
                clock_skew_seconds=0,
            )
        )
    )


def test_mcp_token_verifier_carries_normalized_principal_claim() -> None:
    private_key, public_key = keypair()
    raw_token = jwt.encode(claims(), private_key, algorithm="RS256")

    access_token = asyncio.run(verifier(public_key).verify_token(raw_token))

    assert access_token is not None
    assert access_token.client_id == "99999999-8888-7777-6666-555555555555"
    assert access_token.subject == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert access_token.claims is not None
    principal = access_token.claims["contextplane_principal"]
    assert principal["tenant_id"] == TENANT
    assert principal["kind"] == PrincipalKind.USER.value


def test_mcp_token_verifier_rejects_invalid_entra_token() -> None:
    _, public_key = keypair()

    assert asyncio.run(verifier(public_key).verify_token("not-a-jwt")) is None


def test_mcp_token_verifier_rejects_token_without_resolve_permission() -> None:
    private_key, public_key = keypair()
    raw_token = jwt.encode(
        claims(scp=None, roles=["Context.Reader"]),
        private_key,
        algorithm="RS256",
    )

    assert asyncio.run(verifier(public_key).verify_token(raw_token)) is None


def test_mcp_token_verifier_accepts_app_role_as_resolve_permission() -> None:
    private_key, public_key = keypair()
    raw_token = jwt.encode(
        claims(
            scp=None,
            idtyp="app",
            roles=["context.resolve"],
        ),
        private_key,
        algorithm="RS256",
    )

    access_token = asyncio.run(verifier(public_key).verify_token(raw_token))

    assert access_token is not None
    assert "context.resolve" in access_token.scopes

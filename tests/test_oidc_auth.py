from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from contextplane.auth import (
    AuthenticationError,
    OIDCValidatorConfig,
    PrincipalKind,
    StaticKeyOIDCValidator,
)

ISSUER = "https://issuer.example.test"
AUDIENCE = "contextplane"


@pytest.fixture(scope="module")
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
        "sub": "user-123",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "tenant_id": "tenant-a",
        "principal_type": "user",
        "roles": ["developer"],
        "groups": ["platform"],
        "scope": "context.read context.resolve",
    }
    payload.update(overrides)
    return payload


def validator(public_key: str) -> StaticKeyOIDCValidator:
    return StaticKeyOIDCValidator(
        OIDCValidatorConfig(
            issuer=ISSUER,
            audience=AUDIENCE,
            public_key_pem=public_key,
            clock_skew_seconds=0,
        )
    )


def token(private_key: str, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, private_key, algorithm="RS256")


def test_valid_user_token_normalizes_principal(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair

    principal = validator(public_key).validate(token(private_key, claims()))

    assert principal.tenant_id == "tenant-a"
    assert principal.subject == "user-123"
    assert principal.kind is PrincipalKind.USER
    assert principal.client_id is None
    assert principal.roles == {"developer"}
    assert principal.groups == {"platform"}
    assert principal.scopes == {"context.read", "context.resolve"}


@pytest.mark.parametrize("kind", [PrincipalKind.AGENT, PrincipalKind.SERVICE])
def test_non_user_principal_requires_and_preserves_client_id(
    keypair: tuple[str, str],
    kind: PrincipalKind,
) -> None:
    private_key, public_key = keypair

    principal = validator(public_key).validate(
        token(
            private_key,
            claims(
                sub=f"{kind.value}-subject",
                principal_type=kind.value,
                client_id=f"{kind.value}-client",
            ),
        )
    )

    assert principal.kind is kind
    assert principal.client_id == f"{kind.value}-client"


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"tenant_id": None}, "token validation failed"),
        ({"tenant_id": "   "}, "token validation failed"),
        ({"principal_type": "robot"}, "token validation failed"),
        ({"principal_type": "agent", "client_id": None}, "token validation failed"),
        ({"roles": "developer"}, "token validation failed"),
        ({"groups": [""]}, "token validation failed"),
        ({"scope": ["context.read"]}, "token validation failed"),
    ],
)
def test_invalid_identity_claims_fail_closed(
    keypair: tuple[str, str],
    override: dict[str, Any],
    match: str,
) -> None:
    private_key, public_key = keypair

    with pytest.raises(AuthenticationError, match=match):
        validator(public_key).validate(token(private_key, claims(**override)))


def test_wrong_issuer_fails_closed(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(
            token(private_key, claims(iss="https://other.example.test"))
        )


def test_wrong_audience_fails_closed(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(token(private_key, claims(aud="other-api")))


def test_expired_token_fails_closed(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair
    now = datetime.now(UTC)

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(
            token(
                private_key,
                claims(
                    iat=int((now - timedelta(minutes=10)).timestamp()),
                    exp=int((now - timedelta(minutes=5)).timestamp()),
                ),
            )
        )


def test_missing_required_standard_claim_fails_closed(
    keypair: tuple[str, str],
) -> None:
    private_key, public_key = keypair
    payload = claims()
    payload.pop("exp")

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(token(private_key, payload))


def test_wrong_signature_fails_closed(keypair: tuple[str, str]) -> None:
    _, public_key = keypair
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_pem = other_private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(token(other_private_pem, claims()))


def test_algorithm_confusion_is_rejected(keypair: tuple[str, str]) -> None:
    _, public_key = keypair
    forged = jwt.encode(claims(), "not-the-rsa-key", algorithm="HS256")

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(forged)


def test_future_issued_at_fails_closed(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair
    now = datetime.now(UTC)

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(
            token(
                private_key,
                claims(
                    iat=int((now + timedelta(minutes=5)).timestamp()),
                    exp=int((now + timedelta(minutes=10)).timestamp()),
                ),
            )
        )


def test_blank_subject_fails_closed(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(token(private_key, claims(sub="   ")))

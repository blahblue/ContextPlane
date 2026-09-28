from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from contextplane.auth import AuthenticationError, PrincipalKind
from contextplane.auth.entra import (
    EntraValidatorConfig,
    StaticKeyEntraValidator,
    principal_from_entra_claims,
)

TENANT = "11111111-2222-3333-4444-555555555555"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
AUDIENCE = "api://contextplane"


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
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "tid": TENANT,
        "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azp": "99999999-8888-7777-6666-555555555555",
        "scp": "context.read context.resolve",
        "roles": ["Context.Reader"],
        "groups": ["group-a", "group-b"],
    }
    payload.update(overrides)
    return payload


def validator(public_key: str) -> StaticKeyEntraValidator:
    return StaticKeyEntraValidator(
        EntraValidatorConfig(
            tenant_id=TENANT,
            issuer=ISSUER,
            audience=AUDIENCE,
            public_key_pem=public_key,
            clock_skew_seconds=0,
        )
    )


def token(private_key: str, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, private_key, algorithm="RS256")


def test_delegated_user_maps_oid_tid_azp_and_scp() -> None:
    principal = principal_from_entra_claims(
        claims(),
        expected_tenant_id=TENANT,
    )

    assert principal.kind is PrincipalKind.USER
    assert principal.tenant_id == TENANT
    assert principal.subject == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert principal.client_id == "99999999-8888-7777-6666-555555555555"
    assert principal.scopes == {"context.read", "context.resolve"}
    assert principal.roles == {"Context.Reader"}
    assert principal.groups == {"group-a", "group-b"}


def test_app_only_token_maps_to_service() -> None:
    principal = principal_from_entra_claims(
        claims(idtyp="app", scp=None, roles=["Context.Resolve"]),
        expected_tenant_id=TENANT,
    )

    assert principal.kind is PrincipalKind.SERVICE
    assert principal.scopes == frozenset()
    assert principal.roles == {"Context.Resolve"}


def test_agent_identity_token_maps_to_agent() -> None:
    principal = principal_from_entra_claims(
        claims(
            idtyp="app",
            scp=None,
            xms_act_fct="11",
            xms_sub_fct="11",
        ),
        expected_tenant_id=TENANT,
    )

    assert principal.kind is PrincipalKind.AGENT


def test_agent_user_account_token_remains_user_with_agent_client() -> None:
    principal = principal_from_entra_claims(
        claims(
            idtyp="user",
            xms_act_fct="11",
            xms_sub_fct="13",
        ),
        expected_tenant_id=TENANT,
    )

    assert principal.kind is PrincipalKind.USER
    assert principal.client_id == "99999999-8888-7777-6666-555555555555"


@pytest.mark.parametrize(
    "override",
    [
        {"tid": "other-tenant"},
        {"tid": None},
        {"oid": None},
        {"oid": 123},
        {"azp": None, "appid": None},
        {"azp": "client-a", "appid": "client-b"},
        {"groups": "group-a"},
        {"roles": "Context.Reader"},
        {"scp": ["context.read"]},
    ],
)
def test_invalid_entra_identity_claims_fail_closed(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        principal_from_entra_claims(
            claims(**override),
            expected_tenant_id=TENANT,
        )


def test_ambiguous_non_user_token_without_idtyp_fails_closed() -> None:
    with pytest.raises(ValueError, match="determine Entra principal type"):
        principal_from_entra_claims(
            claims(scp=None, idtyp=None),
            expected_tenant_id=TENANT,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"hasgroups": True, "groups": None},
        {
            "groups": None,
            "_claim_names": {"groups": "src1"},
            "_claim_sources": {
                "src1": {"endpoint": "https://graph.example.test/memberObjects"}
            },
        },
    ],
)
def test_group_overage_fails_closed_until_graph_resolution_exists(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="group overage"):
        principal_from_entra_claims(
            claims(**overrides),
            expected_tenant_id=TENANT,
        )


def test_signed_entra_token_validates_end_to_end(keypair: tuple[str, str]) -> None:
    private_key, public_key = keypair

    principal = validator(public_key).validate(token(private_key, claims()))

    assert principal.kind is PrincipalKind.USER
    assert principal.tenant_id == TENANT


def test_wrong_tenant_fails_as_generic_authentication_error(
    keypair: tuple[str, str],
) -> None:
    private_key, public_key = keypair

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(
            token(private_key, claims(tid="other-tenant"))
        )


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


def test_hs256_algorithm_confusion_fails_closed(keypair: tuple[str, str]) -> None:
    _, public_key = keypair
    forged = jwt.encode(claims(), "not-rsa", algorithm="HS256")

    with pytest.raises(AuthenticationError, match="token validation failed"):
        validator(public_key).validate(forged)


def test_contradictory_agent_marker_claims_fail_closed() -> None:
    with pytest.raises(ValueError, match="claims disagree"):
        principal_from_entra_claims(
            claims(
                idtyp="app",
                scp=None,
                xms_act_fct="11",
                xms_sub_fct="13",
            ),
            expected_tenant_id=TENANT,
        )


def test_mutable_display_identity_claims_are_ignored_for_authorization() -> None:
    principal = principal_from_entra_claims(
        claims(
            preferred_username="attacker-controlled@example.test",
            name="Mutable Display Name",
        ),
        expected_tenant_id=TENANT,
    )

    assert principal.subject == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

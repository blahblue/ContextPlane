from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from contextplane.api.dependencies import authenticate_principal, get_policy_rules
from contextplane.app import app
from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextItemCreate,
    ContextScope,
    ContextSource,
    OverridePolicy,
    SensitivityLevel,
    SourceType,
)
from contextplane.context_registry.repository import create_context_item
from contextplane.database import build_engine
from contextplane.policy import PolicyEffect, PolicyRule
from contextplane.settings import Settings

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


def principal(tenant_id: str, subject: str = "user-123") -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="client-123",
        roles=frozenset({"developer"}),
        groups=frozenset({"platform"}),
        scopes=frozenset({"context.resolve"}),
    )


def context_item(
    *,
    tenant_id: str,
    key: str,
    value: str,
    checksum_char: str,
    user_id: str | None = None,
    application: str | None = None,
    domain: ContextDomain = ContextDomain.ENGINEERING,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": value},
        domain=domain,
        scope=ContextScope(
            tenant_id=tenant_id,
            user_id=user_id,
            application=application,
        ),
        owner="api-test-owner",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def post(client: TestClient, body: dict[str, object]) -> object:
    return client.post(
        "/v1/context/resolve",
        headers={"Authorization": "Bearer ignored-by-test-override"},
        json=body,
    )


@pytest.fixture
def engine():
    db_engine = build_engine(Settings())
    try:
        yield db_engine
    finally:
        db_engine.dispose()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def authenticate_as(value: Principal) -> None:
    app.dependency_overrides[authenticate_principal] = lambda: value


def set_policy_rules(*rules: PolicyRule) -> None:
    app.dependency_overrides[get_policy_rules] = lambda: tuple(rules)


def test_missing_bearer_returns_401_before_provider_configuration() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/context/resolve",
        json={"domains": ["engineering"]},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_presented_bearer_fails_unavailable_when_auth_provider_is_unconfigured() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/context/resolve",
        headers={"Authorization": "Bearer unvalidated-token"},
        json={"domains": ["engineering"]},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication provider is not configured"}


def test_authenticated_resolution_is_tenant_and_identity_scoped(engine) -> None:
    tenant_id = f"api-{uuid4()}"
    other_tenant = f"api-other-{uuid4()}"
    user_id = "user-123"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.global",
                value="global",
                checksum_char="a",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.personal",
                value="personal",
                checksum_char="b",
                user_id=user_id,
                application="client-123",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.other-user",
                value="hidden",
                checksum_char="c",
                user_id="user-999",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=other_tenant,
                key="engineering.other-tenant",
                value="hidden",
                checksum_char="d",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    client = TestClient(app)
    response = post(client, {"domains": ["engineering"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == tenant_id
    assert [item["key"] for item in payload["context"]] == [
        "engineering.global",
        "engineering.personal",
    ]
    assert all(item["provenance"]["owner"] == "api-test-owner" for item in payload["context"])
    assert {
        item["provenance"]["source_identifier"] for item in payload["context"]
    } == {
        "engineering.global-a",
        "engineering.personal-b",
    }
    assert "source_uri" not in payload["context"][0]["provenance"]


def test_body_cannot_supply_identity_scope() -> None:
    tenant_id = f"api-identity-{uuid4()}"
    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = post(
        client,
        {
            "domains": ["engineering"],
            "tenant_id": "attacker-tenant",
            "user_id": "other-user",
            "repository": "sensitive-repo",
            "resource": "sensitive-resource",
        },
    )

    assert response.status_code == 422


def test_policy_narrowing_filters_before_effective_context(engine) -> None:
    tenant_id = f"api-narrow-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.allowed",
                value="allowed",
                checksum_char="e",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.hidden",
                value="hidden",
                checksum_char="f",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    set_policy_rules(
        PolicyRule(
            rule_id="narrow-engineering",
            tenant_id=tenant_id,
            authority_level=AuthorityLevel.POLICY,
            effect=PolicyEffect.NARROW,
            target_domains=frozenset({ContextDomain.ENGINEERING}),
            allowed_keys=frozenset({"engineering.allowed"}),
            reason="only approved engineering context",
        )
    )
    client = TestClient(app)

    response = post(client, {"domains": ["engineering"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"]["decision"] == "narrow"
    assert [item["key"] for item in payload["context"]] == ["engineering.allowed"]


def test_policy_deny_returns_no_context(engine) -> None:
    tenant_id = f"api-deny-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="security.hidden",
                value="hidden",
                checksum_char="1",
                domain=ContextDomain.SECURITY,
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    set_policy_rules(
        PolicyRule(
            rule_id="deny-security",
            tenant_id=tenant_id,
            authority_level=AuthorityLevel.MANDATORY_CONTROL,
            effect=PolicyEffect.DENY,
            target_domains=frozenset({ContextDomain.SECURITY}),
            reason="security context unavailable to this surface",
        )
    )
    client = TestClient(app)

    response = post(client, {"domains": ["security"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"]["decision"] == "deny"
    assert payload["context"] == []
    assert payload["candidate_explanations"] == []
    assert payload["conflict_decisions"] == []


def test_requested_keys_are_monotonic_and_do_not_broaden(engine) -> None:
    tenant_id = f"api-keys-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.one",
                value="one",
                checksum_char="2",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.two",
                value="two",
                checksum_char="3",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = post(
        client,
        {
            "domains": ["engineering"],
            "keys": ["engineering.one"],
        },
    )

    assert response.status_code == 200
    assert [item["key"] for item in response.json()["context"]] == [
        "engineering.one"
    ]


def test_exact_governance_conflict_fails_closed_with_409(engine) -> None:
    tenant_id = f"api-conflict-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                value="left",
                checksum_char="4",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                value="right",
                checksum_char="5",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = post(client, {"domains": ["engineering"]})

    assert response.status_code == 409
    assert response.json() == {"detail": "context governance conflict"}


def test_foreign_tenant_policy_configuration_fails_closed(engine) -> None:
    tenant_id = f"api-policy-tenant-{uuid4()}"

    authenticate_as(principal(tenant_id))
    set_policy_rules(
        PolicyRule(
            rule_id="wrong-tenant-rule",
            tenant_id="other-tenant",
            authority_level=AuthorityLevel.POLICY,
            effect=PolicyEffect.ALLOW,
            target_domains=frozenset({ContextDomain.ENGINEERING}),
            reason="misconfigured",
        )
    )
    client = TestClient(app)

    response = post(client, {"domains": ["engineering"]})

    assert response.status_code == 500
    assert response.json() == {"detail": "policy configuration is invalid"}

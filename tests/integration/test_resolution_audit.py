from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from contextplane.api.dependencies import authenticate_principal, get_policy_rules
from contextplane.app import app
from contextplane.audit.db import ResolutionAuditRecord
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


def principal(
    tenant_id: str,
    *,
    subject: str = "audit-user",
    client_id: str = "audit-client",
) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id=client_id,
        scopes=frozenset({"context.resolve"}),
    )


def authenticate_as(value: Principal) -> None:
    app.dependency_overrides[authenticate_principal] = lambda: value


def set_policy_rules(*rules: PolicyRule) -> None:
    app.dependency_overrides[get_policy_rules] = lambda: tuple(rules)


def context_item(
    *,
    tenant_id: str,
    key: str,
    checksum_char: str,
    value: str,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": value},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(tenant_id=tenant_id),
        owner="audit-test-owner",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"audit-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def resolve(client: TestClient, body: dict[str, object]):
    return client.post(
        "/v1/context/resolve",
        headers={"Authorization": "Bearer test-override"},
        json=body,
    )


def test_successful_resolution_persists_secret_minimized_audit(engine) -> None:
    tenant_id = f"audit-success-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.audit",
                checksum_char="a",
                value="visible-context-value",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = resolve(
        client,
        {
            "domains": ["engineering"],
            "task": "sensitive-task-value",
            "keys": ["engineering.audit"],
        },
    )

    assert response.status_code == 200
    resolution_id = UUID(response.json()["resolution_id"])

    with Session(engine) as session:
        record = session.get(ResolutionAuditRecord, resolution_id)
        assert record is not None
        assert record.tenant_id == tenant_id
        assert record.outcome == "allowed"
        assert record.requested_key_count == 1
        assert record.selector_dimensions == ["task"]
        assert "sensitive-task-value" not in str(record.selector_dimensions)
        assert "visible-context-value" not in str(record.returned_items)
        assert record.returned_items[0]["record_id"]
        assert record.returned_items[0]["logical_id"]

    lookup = client.get(
        f"/v1/context/resolutions/{resolution_id}",
        headers={"Authorization": "Bearer test-override"},
    )

    assert lookup.status_code == 200
    payload = lookup.json()
    assert payload["resolution_id"] == str(resolution_id)
    assert payload["outcome"] == "allowed"
    assert payload["selector_dimensions"] == ["task"]
    assert "principal_subject" not in payload
    assert "client_id" not in payload


def test_denied_resolution_is_audited_with_policy_rule_id(engine) -> None:
    tenant_id = f"audit-deny-{uuid4()}"
    authenticate_as(principal(tenant_id))
    set_policy_rules(
        PolicyRule(
            rule_id="deny-engineering",
            tenant_id=tenant_id,
            authority_level=AuthorityLevel.MANDATORY_CONTROL,
            effect=PolicyEffect.DENY,
            target_domains=frozenset({ContextDomain.ENGINEERING}),
            reason="not available",
        )
    )
    client = TestClient(app)

    response = resolve(client, {"domains": ["engineering"]})

    assert response.status_code == 200
    resolution_id = UUID(response.json()["resolution_id"])

    with Session(engine) as session:
        record = session.get(ResolutionAuditRecord, resolution_id)
        assert record is not None
        assert record.outcome == "denied"
        assert record.policy_decision == "deny"
        assert record.policy_rule_ids == ["deny-engineering"]
        assert record.returned_items == []


def test_governance_conflict_is_audited_and_returns_correlation_header(engine) -> None:
    tenant_id = f"audit-conflict-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                checksum_char="b",
                value="left",
            ),
        )
        create_context_item(
            session,
            context_item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                checksum_char="c",
                value="right",
            ),
        )
        session.commit()

    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = resolve(client, {"domains": ["engineering"]})

    assert response.status_code == 409
    resolution_id = UUID(response.headers["x-contextplane-resolution-id"])

    with Session(engine) as session:
        record = session.get(ResolutionAuditRecord, resolution_id)
        assert record is not None
        assert record.outcome == "conflict"
        assert record.error_code == "context_governance_conflict"
        assert len(record.considered_record_ids) == 2
        assert record.returned_items == []


def test_audit_lookup_is_scoped_to_exact_authenticated_actor(engine) -> None:
    tenant_id = f"audit-owner-{uuid4()}"
    owner = principal(tenant_id, subject="owner", client_id="client-a")
    authenticate_as(owner)
    client = TestClient(app)

    response = resolve(client, {"domains": ["engineering"]})
    assert response.status_code == 200
    resolution_id = response.json()["resolution_id"]

    authenticate_as(principal(tenant_id, subject="other-user", client_id="client-a"))
    assert (
        client.get(
            f"/v1/context/resolutions/{resolution_id}",
            headers={"Authorization": "Bearer test-override"},
        ).status_code
        == 404
    )

    authenticate_as(principal(tenant_id, subject="owner", client_id="client-b"))
    assert (
        client.get(
            f"/v1/context/resolutions/{resolution_id}",
            headers={"Authorization": "Bearer test-override"},
        ).status_code
        == 404
    )


def test_database_rejects_audit_update_and_delete(engine) -> None:
    tenant_id = f"audit-immutable-{uuid4()}"
    authenticate_as(principal(tenant_id))
    client = TestClient(app)

    response = resolve(client, {"domains": ["engineering"]})
    assert response.status_code == 200
    resolution_id = UUID(response.json()["resolution_id"])

    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="resolution audit records are immutable"):
            session.execute(
                update(ResolutionAuditRecord)
                .where(ResolutionAuditRecord.resolution_id == resolution_id)
                .values(outcome="denied")
            )
            session.commit()
        session.rollback()

    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="resolution audit records are immutable"):
            session.execute(
                delete(ResolutionAuditRecord).where(
                    ResolutionAuditRecord.resolution_id == resolution_id
                )
            )
            session.commit()
        session.rollback()

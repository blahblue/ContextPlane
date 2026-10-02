from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from contextplane.api.dependencies import authenticate_principal
from contextplane.app import app
from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry.db import ContextItemRecord
from contextplane.database import build_engine
from contextplane.publishing import PublicationPermission
from contextplane.publishing.db import PublicationAuditRecord
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
    subject: str = "publisher-a",
    permissions: frozenset[str] = frozenset(),
) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="publishing-client",
        scopes=permissions,
    )


def authenticate_as(value: Principal) -> None:
    app.dependency_overrides[authenticate_principal] = lambda: value


def body(
    *,
    authority: str = "standard",
    key: str = "engineering.publishing",
    user_id: str | None = None,
    value: str = "v1",
) -> dict[str, object]:
    scope: dict[str, object] = {"repository": "checkout-api"}
    if user_id is not None:
        scope["user_id"] = user_id
    return {
        "key": key,
        "value": {"value": value},
        "domain": "engineering",
        "scope": scope,
        "owner": "platform-engineering",
        "source": {
            "type": "api",
            "identifier": "publishing-integration",
        },
        "authority_level": authority,
        "effective_from": (NOW - timedelta(minutes=1)).isoformat(),
        "sensitivity": "internal",
        "override_policy": "deny",
    }


def publish(
    client: TestClient,
    *,
    payload: dict[str, object],
    idem: str,
):
    return client.post(
        "/v1/context/items",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": idem,
        },
        json=payload,
    )


def test_create_derives_tenant_and_publisher_and_is_idempotent(engine) -> None:
    tenant = f"publish-{uuid4()}"
    actor = principal(
        tenant,
        permissions=frozenset({PublicationPermission.STANDARD.value}),
    )
    authenticate_as(actor)
    client = TestClient(app)

    first = publish(client, payload=body(), idem="create-standard-1")
    second = publish(client, payload=body(), idem="create-standard-1")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()

    record_id = UUID(first.json()["record_id"])
    publication_id = UUID(first.json()["publication_id"])

    with Session(engine) as session:
        record = session.get(ContextItemRecord, record_id)
        audit = session.get(PublicationAuditRecord, publication_id)

    assert record is not None
    assert record.tenant_id == tenant
    assert record.publisher_subject == "publisher-a"
    assert record.publisher_kind == "user"
    assert record.publisher_client_id == "publishing-client"
    assert record.publication_action == "create"
    assert record.publication_permission == PublicationPermission.STANDARD.value
    assert audit is not None
    assert audit.outcome == "succeeded"
    assert audit.context_record_id == record_id
    assert audit.request_hash
    assert audit.idempotency_key_hash
    assert "v1" not in audit.request_hash


def test_request_cannot_supply_tenant_or_publisher_identity() -> None:
    tenant = f"publish-extra-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            permissions=frozenset({PublicationPermission.STANDARD.value}),
        )
    )
    client = TestClient(app)
    payload = body()
    payload["tenant_id"] = "victim"
    payload["publisher_subject"] = "victim-user"

    response = publish(client, payload=payload, idem="identity-injection")

    assert response.status_code == 422


def test_denied_publication_is_durably_audited(engine) -> None:
    tenant = f"publish-denied-{uuid4()}"
    authenticate_as(principal(tenant))
    client = TestClient(app)

    response = publish(client, payload=body(), idem="denied-standard")

    assert response.status_code == 403
    publication_id = UUID(response.headers["x-contextplane-publication-id"])

    with Session(engine) as session:
        audit = session.get(PublicationAuditRecord, publication_id)

    assert audit is not None
    assert audit.tenant_id == tenant
    assert audit.outcome == "denied"
    assert audit.error_code == "not_authorized"
    assert audit.context_record_id is None
    assert audit.permission_used is None


def test_self_preference_can_only_target_authenticated_user(engine) -> None:
    tenant = f"publish-self-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            subject="user-a",
            permissions=frozenset({PublicationPermission.PREFERENCE_SELF.value}),
        )
    )
    client = TestClient(app)

    own = publish(
        client,
        payload=body(
            authority="preference",
            user_id="user-a",
            key="engineering.preference.own",
        ),
        idem="self-own",
    )
    other = publish(
        client,
        payload=body(
            authority="preference",
            user_id="user-b",
            key="engineering.preference.other",
        ),
        idem="self-other",
    )

    assert own.status_code == 201
    assert other.status_code == 403


def test_idempotency_key_reuse_with_changed_request_conflicts() -> None:
    tenant = f"publish-idem-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            permissions=frozenset({PublicationPermission.STANDARD.value}),
        )
    )
    client = TestClient(app)

    first = publish(client, payload=body(value="one"), idem="same-key")
    changed = publish(client, payload=body(value="two"), idem="same-key")

    assert first.status_code == 201
    assert changed.status_code == 409
    assert (
        changed.headers["x-contextplane-publication-id"]
        == first.json()["publication_id"]
    )


def test_supersede_preserves_authority_and_publisher_provenance(engine) -> None:
    tenant = f"publish-super-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            permissions=frozenset({PublicationPermission.STANDARD.value}),
        )
    )
    client = TestClient(app)

    created = publish(client, payload=body(value="v1"), idem="super-create")
    previous_id = created.json()["record_id"]
    replacement = client.post(
        f"/v1/context/items/{previous_id}/supersede",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "super-v2",
        },
        json=body(value="v2"),
    )

    assert replacement.status_code == 201
    assert replacement.json()["version"] == 2
    assert replacement.json()["logical_id"] == created.json()["logical_id"]

    with Session(engine) as session:
        row = session.get(ContextItemRecord, UUID(replacement.json()["record_id"]))

    assert row is not None
    assert row.publisher_subject == "publisher-a"
    assert row.publication_action == "supersede"
    assert row.publication_permission == PublicationPermission.STANDARD.value


def test_supersede_cannot_change_authority_without_approval_workflow() -> None:
    tenant = f"publish-authority-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            permissions=frozenset(
                {
                    PublicationPermission.STANDARD.value,
                    PublicationPermission.PREFERENCE.value,
                }
            ),
        )
    )
    client = TestClient(app)

    created = publish(client, payload=body(), idem="authority-create")
    changed = client.post(
        f"/v1/context/items/{created.json()['record_id']}/supersede",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "authority-change",
        },
        json=body(authority="preference"),
    )

    assert changed.status_code == 409


def test_publication_audit_is_immutable(engine) -> None:
    tenant = f"publish-immutable-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            permissions=frozenset({PublicationPermission.STANDARD.value}),
        )
    )
    response = publish(TestClient(app), payload=body(), idem="immutable")
    publication_id = UUID(response.json()["publication_id"])

    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="publication audit records are immutable"):
            session.execute(
                update(PublicationAuditRecord)
                .where(PublicationAuditRecord.publication_id == publication_id)
                .values(outcome="denied")
            )
            session.commit()
        session.rollback()

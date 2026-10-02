from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from contextplane.api.dependencies import authenticate_principal, get_settings
from contextplane.app import app
from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry.db import ContextItemRecord
from contextplane.database import build_engine
from contextplane.publishing import (
    PublicationApprovalPermission,
    PublicationPermission,
)
from contextplane.publishing.approval_db import (
    PublicationApprovalEventRecord,
    PublicationProposalRecord,
)
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
    subject: str,
    permissions: frozenset[str],
) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="approval-workflow-client",
        scopes=permissions,
    )


def authenticate_as(value: Principal) -> None:
    app.dependency_overrides[authenticate_principal] = lambda: value


def context_body(
    *,
    authority: str = "policy",
    key: str = "security.approved-policy",
    value: str = "approved",
) -> dict[str, object]:
    return {
        "key": key,
        "value": {"value": value},
        "domain": "security",
        "scope": {"environment": "production"},
        "owner": "security-governance",
        "source": {"identifier": "approval-workflow-test"},
        "authority_level": authority,
        "effective_from": (NOW - timedelta(minutes=1)).isoformat(),
        "sensitivity": "internal",
        "override_policy": "deny",
    }


def create_proposal(
    client: TestClient,
    *,
    payload: dict[str, object],
    idem: str,
    action: str = "create",
    previous_id: str | None = None,
):
    request: dict[str, object] = {
        "action": action,
        "context": payload,
    }
    if previous_id is not None:
        request["previous_id"] = previous_id
    return client.post(
        "/v1/context/publication-proposals",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": idem,
        },
        json=request,
    )


def test_direct_high_authority_write_requires_approval(engine) -> None:
    tenant = f"approval-direct-{uuid4()}"
    authenticate_as(
        principal(
            tenant,
            subject="publisher",
            permissions=frozenset({PublicationPermission.POLICY.value}),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/v1/context/items",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "direct-policy",
        },
        json=context_body(),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "high-authority publication requires approval workflow"
    )

    with Session(engine) as session:
        rows = session.scalars(
            select(ContextItemRecord).where(ContextItemRecord.tenant_id == tenant)
        ).all()
    assert rows == []


def test_policy_proposal_moves_draft_approved_active(engine) -> None:
    tenant = f"approval-lifecycle-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    approver = principal(
        tenant,
        subject="approver",
        permissions=frozenset(
            {PublicationApprovalPermission.APPROVE_POLICY.value}
        ),
    )
    activator = principal(
        tenant,
        subject="activator",
        permissions=frozenset(
            {PublicationApprovalPermission.ACTIVATE_POLICY.value}
        ),
    )
    client = TestClient(app)

    authenticate_as(publisher)
    draft = create_proposal(
        client,
        payload=context_body(),
        idem="policy-lifecycle",
    )

    assert draft.status_code == 201
    assert draft.json()["state"] == "draft"
    proposal_id = draft.json()["proposal_id"]

    with Session(engine) as session:
        assert session.scalars(
            select(ContextItemRecord).where(ContextItemRecord.tenant_id == tenant)
        ).all() == []

    authenticate_as(approver)
    approved = client.post(
        f"/v1/context/publication-proposals/{proposal_id}/approve",
        headers={"Authorization": "Bearer test"},
    )

    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert approved.json()["approval_event_id"]

    with Session(engine) as session:
        assert session.scalars(
            select(ContextItemRecord).where(ContextItemRecord.tenant_id == tenant)
        ).all() == []

    authenticate_as(activator)
    active = client.post(
        f"/v1/context/publication-proposals/{proposal_id}/activate",
        headers={"Authorization": "Bearer test"},
    )

    assert active.status_code == 200
    assert active.json()["state"] == "active"
    assert active.json()["activation_event_id"]
    assert active.json()["context_record_id"]
    assert active.json()["version"] == 1

    with Session(engine) as session:
        row = session.get(
            ContextItemRecord,
            UUID(active.json()["context_record_id"]),
        )
        events = session.scalars(
            select(PublicationApprovalEventRecord).where(
                PublicationApprovalEventRecord.proposal_id
                == UUID(proposal_id)
            )
        ).all()

    assert row is not None
    assert row.authority_level == "policy"
    assert row.publisher_subject == "publisher"
    assert row.publication_permission == PublicationPermission.POLICY.value
    succeeded = [event for event in events if event.outcome == "succeeded"]
    assert {event.event_type for event in succeeded} == {"approve", "activate"}
    assert {event.actor_subject for event in succeeded} == {
        "approver",
        "activator",
    }


def test_publisher_cannot_self_approve_by_default(engine) -> None:
    tenant = f"approval-separation-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset(
            {
                PublicationPermission.POLICY.value,
                PublicationApprovalPermission.APPROVE_POLICY.value,
            }
        ),
    )
    authenticate_as(publisher)
    client = TestClient(app)

    draft = create_proposal(
        client,
        payload=context_body(),
        idem="self-approval-default",
    )
    proposal_id = draft.json()["proposal_id"]

    response = client.post(
        f"/v1/context/publication-proposals/{proposal_id}/approve",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403
    assert response.headers["x-contextplane-approval-event-id"]

    with Session(engine) as session:
        event = session.get(
            PublicationApprovalEventRecord,
            UUID(response.headers["x-contextplane-approval-event-id"]),
        )
    assert event is not None
    assert event.outcome == "denied"
    assert event.error_code == "approval_not_authorized"


def test_self_approval_can_be_explicitly_enabled() -> None:
    tenant = f"approval-separation-off-{uuid4()}"
    actor = principal(
        tenant,
        subject="publisher",
        permissions=frozenset(
            {
                PublicationPermission.POLICY.value,
                PublicationApprovalPermission.APPROVE_POLICY.value,
            }
        ),
    )
    authenticate_as(actor)
    base_settings = Settings()
    app.dependency_overrides[get_settings] = lambda: base_settings.model_copy(
        update={"publishing_require_distinct_approver": False}
    )
    client = TestClient(app)

    draft = create_proposal(
        client,
        payload=context_body(),
        idem="self-approval-enabled",
    )
    response = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/approve",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "approved"


def test_activation_before_approval_fails_closed() -> None:
    tenant = f"approval-before-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    activator = principal(
        tenant,
        subject="activator",
        permissions=frozenset(
            {PublicationApprovalPermission.ACTIVATE_POLICY.value}
        ),
    )
    client = TestClient(app)

    authenticate_as(publisher)
    draft = create_proposal(
        client,
        payload=context_body(),
        idem="activation-before-approval",
    )

    authenticate_as(activator)
    response = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/activate",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 409
    assert response.headers["x-contextplane-approval-event-id"]


def test_policy_approval_permission_cannot_approve_mandatory_control() -> None:
    tenant = f"approval-mandatory-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset(
            {PublicationPermission.MANDATORY_CONTROL.value}
        ),
    )
    wrong_approver = principal(
        tenant,
        subject="policy-approver",
        permissions=frozenset(
            {PublicationApprovalPermission.APPROVE_POLICY.value}
        ),
    )
    client = TestClient(app)

    authenticate_as(publisher)
    draft = create_proposal(
        client,
        payload=context_body(
            authority="mandatory_control",
            key="security.mandatory",
        ),
        idem="mandatory-proposal",
    )

    authenticate_as(wrong_approver)
    response = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/approve",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 403


def test_proposal_idempotency_replays_and_changed_request_conflicts() -> None:
    tenant = f"approval-idem-{uuid4()}"
    actor = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    authenticate_as(actor)
    client = TestClient(app)

    first = create_proposal(
        client,
        payload=context_body(value="one"),
        idem="proposal-idem",
    )
    replay = create_proposal(
        client,
        payload=context_body(value="one"),
        idem="proposal-idem",
    )
    changed = create_proposal(
        client,
        payload=context_body(value="two"),
        idem="proposal-idem",
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["proposal_id"] == first.json()["proposal_id"]
    assert changed.status_code == 409
    assert (
        changed.headers["x-contextplane-proposal-id"]
        == first.json()["proposal_id"]
    )


def test_cross_tenant_proposal_is_not_visible() -> None:
    tenant_a = f"approval-a-{uuid4()}"
    tenant_b = f"approval-b-{uuid4()}"
    publisher = principal(
        tenant_b,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    client = TestClient(app)

    authenticate_as(publisher)
    draft = create_proposal(
        client,
        payload=context_body(),
        idem="tenant-b-proposal",
    )

    attacker = principal(
        tenant_a,
        subject="approver",
        permissions=frozenset(
            {PublicationApprovalPermission.APPROVE_POLICY.value}
        ),
    )
    authenticate_as(attacker)
    response = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/approve",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 404


def test_approved_supersession_can_raise_authority(engine) -> None:
    tenant = f"approval-transition-{uuid4()}"
    standard_publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.STANDARD.value}),
    )
    client = TestClient(app)

    authenticate_as(standard_publisher)
    standard = client.post(
        "/v1/context/items",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "initial-standard",
        },
        json={
            **context_body(
                authority="standard",
                key="security.transition",
                value="standard",
            ),
        },
    )
    assert standard.status_code == 201

    policy_publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    authenticate_as(policy_publisher)
    draft = create_proposal(
        client,
        payload=context_body(
            authority="policy",
            key="security.transition",
            value="policy",
        ),
        idem="raise-to-policy",
        action="supersede",
        previous_id=standard.json()["record_id"],
    )
    assert draft.status_code == 201

    authenticate_as(
        principal(
            tenant,
            subject="approver",
            permissions=frozenset(
                {PublicationApprovalPermission.APPROVE_POLICY.value}
            ),
        )
    )
    assert client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/approve",
        headers={"Authorization": "Bearer test"},
    ).status_code == 200

    authenticate_as(
        principal(
            tenant,
            subject="activator",
            permissions=frozenset(
                {PublicationApprovalPermission.ACTIVATE_POLICY.value}
            ),
        )
    )
    active = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/activate",
        headers={"Authorization": "Bearer test"},
    )

    assert active.status_code == 200
    assert active.json()["version"] == 2

    with Session(engine) as session:
        row = session.get(
            ContextItemRecord,
            UUID(active.json()["context_record_id"]),
        )
    assert row is not None
    assert row.authority_level == "policy"


def test_stale_supersession_proposal_cannot_activate() -> None:
    tenant = f"approval-stale-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset(
            {
                PublicationPermission.STANDARD.value,
                PublicationPermission.POLICY.value,
            }
        ),
    )
    client = TestClient(app)

    authenticate_as(publisher)
    initial = client.post(
        "/v1/context/items",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "stale-initial",
        },
        json=context_body(
            authority="standard",
            key="security.stale-transition",
            value="v1",
        ),
    )
    previous_id = initial.json()["record_id"]

    draft = create_proposal(
        client,
        payload=context_body(
            authority="policy",
            key="security.stale-transition",
            value="future-policy",
        ),
        idem="stale-policy-proposal",
        action="supersede",
        previous_id=previous_id,
    )

    direct_v2 = client.post(
        f"/v1/context/items/{previous_id}/supersede",
        headers={
            "Authorization": "Bearer test",
            "Idempotency-Key": "stale-standard-v2",
        },
        json=context_body(
            authority="standard",
            key="security.stale-transition",
            value="v2",
        ),
    )
    assert direct_v2.status_code == 201

    authenticate_as(
        principal(
            tenant,
            subject="approver",
            permissions=frozenset(
                {PublicationApprovalPermission.APPROVE_POLICY.value}
            ),
        )
    )
    client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/approve",
        headers={"Authorization": "Bearer test"},
    )

    authenticate_as(
        principal(
            tenant,
            subject="activator",
            permissions=frozenset(
                {PublicationApprovalPermission.ACTIVATE_POLICY.value}
            ),
        )
    )
    activation = client.post(
        f"/v1/context/publication-proposals/{draft.json()['proposal_id']}/activate",
        headers={"Authorization": "Bearer test"},
    )

    assert activation.status_code == 409


def test_proposal_and_approval_events_are_immutable(engine) -> None:
    tenant = f"approval-immutable-{uuid4()}"
    publisher = principal(
        tenant,
        subject="publisher",
        permissions=frozenset({PublicationPermission.POLICY.value}),
    )
    client = TestClient(app)
    authenticate_as(publisher)
    draft = create_proposal(
        client,
        payload=context_body(),
        idem="immutable-proposal",
    )
    proposal_id = UUID(draft.json()["proposal_id"])

    with Session(engine) as session:
        with pytest.raises(
            DBAPIError,
            match="publication approval workflow records are immutable",
        ):
            session.execute(
                update(PublicationProposalRecord)
                .where(PublicationProposalRecord.proposal_id == proposal_id)
                .values(authority_level="mandatory_control")
            )
            session.commit()
        session.rollback()

    authenticate_as(
        principal(
            tenant,
            subject="approver",
            permissions=frozenset(
                {PublicationApprovalPermission.APPROVE_POLICY.value}
            ),
        )
    )
    approved = client.post(
        f"/v1/context/publication-proposals/{proposal_id}/approve",
        headers={"Authorization": "Bearer test"},
    )
    event_id = UUID(approved.json()["approval_event_id"])

    with Session(engine) as session:
        with pytest.raises(
            DBAPIError,
            match="publication approval workflow records are immutable",
        ):
            session.execute(
                delete(PublicationApprovalEventRecord).where(
                    PublicationApprovalEventRecord.event_id == event_id
                )
            )
            session.commit()
        session.rollback()

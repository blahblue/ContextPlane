from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_policy_rules,
    get_resolution_cache,
)
from contextplane.app import app
from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import InMemoryResolutionCache
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
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.repository import create_context_item
from contextplane.context_registry.state import get_context_state_snapshot
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


def principal(tenant_id: str, *, subject: str = "cache-user") -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="cache-client",
        roles=frozenset({"developer"}),
        groups=frozenset({"platform"}),
        scopes=frozenset({"context.resolve"}),
    )


def item(
    *,
    tenant_id: str,
    key: str,
    checksum_char: str,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": key},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(tenant_id=tenant_id),
        owner="cache-test-owner",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=effective_from or NOW - timedelta(days=1),
        effective_to=effective_to,
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def configure_runtime(
    tenant_id: str,
    cache: InMemoryResolutionCache,
    *,
    rules: tuple[PolicyRule, ...] = (),
    subject: str = "cache-user",
) -> None:
    identity = principal(tenant_id, subject=subject)
    app.dependency_overrides[authenticate_principal] = lambda: identity
    app.dependency_overrides[get_resolution_cache] = lambda: cache
    app.dependency_overrides[get_policy_rules] = lambda: rules


def post(client: TestClient):
    return client.post(
        "/v1/context/resolve",
        headers={"Authorization": "Bearer test-override"},
        json={"domains": ["engineering"]},
    )


def allow_rule(tenant_id: str, *, reason: str) -> PolicyRule:
    return PolicyRule(
        rule_id="allow-engineering",
        tenant_id=tenant_id,
        authority_level=AuthorityLevel.POLICY,
        effect=PolicyEffect.ALLOW,
        target_domains=frozenset({ContextDomain.ENGINEERING}),
        reason=reason,
    )


def test_repeated_resolution_hits_cache_but_still_gets_new_audit_id(engine) -> None:
    tenant_id = f"cache-hit-{uuid4()}"
    cache = InMemoryResolutionCache(ttl_seconds=300, max_entries=16)

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.cached",
                checksum_char="a",
            ),
        )
        session.commit()

    configure_runtime(tenant_id, cache)
    client = TestClient(app)

    first = post(client)
    second = post(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert cache.misses == 1
    assert cache.hits == 1
    assert first.json()["resolution_id"] != second.json()["resolution_id"]
    assert first.json()["context"] == second.json()["context"]


def test_context_insert_changes_revision_and_invalidates_cache(engine) -> None:
    tenant_id = f"cache-revision-{uuid4()}"
    cache = InMemoryResolutionCache(ttl_seconds=300, max_entries=16)

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.first",
                checksum_char="b",
            ),
        )
        session.commit()

    configure_runtime(tenant_id, cache)
    client = TestClient(app)

    first = post(client)
    assert first.status_code == 200
    assert [entry["key"] for entry in first.json()["context"]] == [
        "engineering.first"
    ]

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.second",
                checksum_char="c",
            ),
        )
        session.commit()

    second = post(client)

    assert second.status_code == 200
    assert [entry["key"] for entry in second.json()["context"]] == [
        "engineering.first",
        "engineering.second",
    ]
    assert cache.misses == 2
    assert cache.hits == 0


def test_policy_fingerprint_invalidates_semantically_same_candidate_query(engine) -> None:
    tenant_id = f"cache-policy-{uuid4()}"
    cache = InMemoryResolutionCache(ttl_seconds=300, max_entries=16)

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.policy-cache",
                checksum_char="d",
            ),
        )
        session.commit()

    configure_runtime(
        tenant_id,
        cache,
        rules=(allow_rule(tenant_id, reason="initial policy text"),),
    )
    client = TestClient(app)
    first = post(client)
    assert first.status_code == 200

    configure_runtime(
        tenant_id,
        cache,
        rules=(allow_rule(tenant_id, reason="updated policy text"),),
    )
    second = post(client)

    assert second.status_code == 200
    assert cache.misses == 2
    assert cache.hits == 0
    assert first.json()["context"] == second.json()["context"]


def test_context_revision_trigger_catches_direct_database_mutation(engine) -> None:
    tenant_id = f"cache-direct-{uuid4()}"

    with Session(engine) as session:
        record = create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.direct",
                checksum_char="e",
            ),
        )
        record_id = record.id
        session.commit()

    with Session(engine) as session:
        before = get_context_state_snapshot(
            session,
            tenant_id=tenant_id,
            as_of=NOW,
        )

    with Session(engine) as session:
        session.execute(
            update(ContextItemRecord)
            .where(ContextItemRecord.id == record_id)
            .values(owner="cache-test-owner-updated")
        )
        session.commit()

    with Session(engine) as session:
        after = get_context_state_snapshot(
            session,
            tenant_id=tenant_id,
            as_of=NOW,
        )

    assert after.revision == before.revision + 1


def test_context_state_tracks_next_effective_time_boundary(engine) -> None:
    tenant_id = f"cache-transition-{uuid4()}"
    future_start = NOW + timedelta(minutes=3)
    future_end = NOW + timedelta(minutes=2)

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.future",
                checksum_char="f",
                effective_from=future_start,
            ),
        )
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.expiring",
                checksum_char="1",
                effective_to=future_end,
            ),
        )
        session.commit()

    with Session(engine) as session:
        snapshot = get_context_state_snapshot(
            session,
            tenant_id=tenant_id,
            as_of=NOW,
        )

    assert snapshot.next_transition == future_end
    assert snapshot.revision >= 2

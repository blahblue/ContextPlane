from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

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
from contextplane.context_registry.repository import (
    create_context_item,
    supersede_context_item,
)
from contextplane.database import build_engine
from contextplane.resolver import ContextResolutionRequest, resolve_context_candidates
from contextplane.settings import Settings

NOW = datetime(2026, 9, 28, 16, 0, tzinfo=UTC)


def item(
    *,
    tenant_id: str,
    key: str,
    checksum: str,
    domain: ContextDomain = ContextDomain.ENGINEERING,
    effective_from: datetime = NOW - timedelta(days=1),
    effective_to: datetime | None = None,
    team: str | None = None,
    role: str | None = None,
    environment: str | None = None,
    value: dict[str, object] | None = None,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value=value or {"rule": checksum[:4]},
        domain=domain,
        scope=ContextScope(
            tenant_id=tenant_id,
            team=team,
            role=role,
            environment=environment,
        ),
        owner="resolver-test",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum[:8]}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=effective_from,
        effective_to=effective_to,
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum,
    )


@pytest.mark.integration
def test_resolver_matches_wildcard_and_specific_scope() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.global",
                    checksum="a" * 64,
                ),
            )
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.platform",
                    checksum="b" * 64,
                    team="platform",
                    environment="production",
                ),
            )
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.other",
                    checksum="c" * 64,
                    team="other",
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(
                        tenant_id=tenant_id,
                        team="platform",
                        environment="production",
                    ),
                    as_of=NOW,
                ),
            )

        assert [candidate.key for candidate in result.candidates] == [
            "engineering.global",
            "engineering.platform",
        ]
        platform = next(
            candidate
            for candidate in result.candidates
            if candidate.key == "engineering.platform"
        )
        assert platform.specificity == 2
        assert platform.matched_dimensions == ("team", "environment")
    finally:
        engine.dispose()


@pytest.mark.integration
def test_required_scope_does_not_match_missing_request_dimension() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-missing-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.production",
                    checksum="d" * 64,
                    environment="production",
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id),
                    as_of=NOW,
                ),
            )

        assert result.candidates == ()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_latest_active_version_selected_before_scope_matching() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-version-{uuid4()}"

    try:
        with Session(engine) as session:
            first = create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.scope-change",
                    checksum="e" * 64,
                ),
            )
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            supersede_context_item(
                session,
                tenant_id=tenant_id,
                previous_id=first_id,
                replacement=item(
                    tenant_id=tenant_id,
                    key="engineering.scope-change",
                    checksum="f" * 64,
                    team="platform",
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id, team="other"),
                    as_of=NOW,
                ),
            )

        assert result.candidates == ()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_future_version_does_not_hide_current_active_version() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-future-{uuid4()}"

    try:
        with Session(engine) as session:
            first = create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.future",
                    checksum="1" * 64,
                    value={"rule": "current"},
                ),
            )
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            supersede_context_item(
                session,
                tenant_id=tenant_id,
                previous_id=first_id,
                replacement=item(
                    tenant_id=tenant_id,
                    key="engineering.future",
                    checksum="2" * 64,
                    effective_from=NOW + timedelta(days=1),
                    value={"rule": "future"},
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id),
                    as_of=NOW,
                ),
            )

        assert len(result.candidates) == 1
        assert result.candidates[0].version == 1
        assert result.candidates[0].value == {"rule": "current"}
    finally:
        engine.dispose()


@pytest.mark.integration
def test_expired_context_is_not_returned() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-expired-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.expired",
                    checksum="3" * 64,
                    effective_from=NOW - timedelta(days=3),
                    effective_to=NOW - timedelta(days=1),
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id),
                    as_of=NOW,
                ),
            )

        assert result.candidates == ()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_domain_filter_and_tenant_boundary() -> None:
    engine = build_engine(Settings())
    tenant_a = f"resolver-a-{uuid4()}"
    tenant_b = f"resolver-b-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_a,
                    key="engineering.visible",
                    checksum="4" * 64,
                    domain=ContextDomain.ENGINEERING,
                ),
            )
            create_context_item(
                session,
                item(
                    tenant_id=tenant_a,
                    key="security.filtered",
                    checksum="5" * 64,
                    domain=ContextDomain.SECURITY,
                ),
            )
            create_context_item(
                session,
                item(
                    tenant_id=tenant_b,
                    key="engineering.other-tenant",
                    checksum="6" * 64,
                    domain=ContextDomain.ENGINEERING,
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_a),
                    domains={ContextDomain.ENGINEERING},
                    as_of=NOW,
                ),
            )

        assert [candidate.key for candidate in result.candidates] == [
            "engineering.visible"
        ]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_candidate_order_is_deterministic() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-order-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="same.key",
                    checksum="7" * 64,
                ),
            )
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="same.key",
                    checksum="8" * 64,
                    team="platform",
                ),
            )
            session.commit()

        request = ContextResolutionRequest(
            scope=ContextScope(tenant_id=tenant_id, team="platform"),
            as_of=NOW,
        )
        with Session(engine) as session:
            first = resolve_context_candidates(session, request)
            second = resolve_context_candidates(session, request)

        assert [candidate.record_id for candidate in first.candidates] == [
            candidate.record_id for candidate in second.candidates
        ]
        assert [candidate.specificity for candidate in first.candidates] == [1, 0]
        assert len(first.explanations) == len(first.candidates)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_expired_newer_version_does_not_reactivate_older_version() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-no-reactivation-{uuid4()}"

    try:
        with Session(engine) as session:
            first = create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="security.retired",
                    checksum="9" * 64,
                    domain=ContextDomain.SECURITY,
                    value={"rule": "old"},
                ),
            )
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            supersede_context_item(
                session,
                tenant_id=tenant_id,
                previous_id=first_id,
                replacement=item(
                    tenant_id=tenant_id,
                    key="security.retired",
                    checksum="0" * 64,
                    domain=ContextDomain.SECURITY,
                    effective_from=NOW - timedelta(hours=2),
                    effective_to=NOW - timedelta(hours=1),
                    value={"rule": "retired"},
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id),
                    as_of=NOW,
                ),
            )

        assert result.candidates == ()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_explicit_empty_domain_filter_returns_no_context() -> None:
    engine = build_engine(Settings())
    tenant_id = f"resolver-empty-domain-{uuid4()}"

    try:
        with Session(engine) as session:
            create_context_item(
                session,
                item(
                    tenant_id=tenant_id,
                    key="engineering.should-not-return",
                    checksum="a1" * 32,
                ),
            )
            session.commit()

        with Session(engine) as session:
            result = resolve_context_candidates(
                session,
                ContextResolutionRequest(
                    scope=ContextScope(tenant_id=tenant_id),
                    domains=frozenset(),
                    as_of=NOW,
                ),
            )

        assert result.candidates == ()
    finally:
        engine.dispose()

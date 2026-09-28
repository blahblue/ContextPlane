from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.repository import (
    ContextIdentityMismatchError,
    ContextItemNotFoundError,
    ContextVersionConflictError,
    create_context_item,
    get_context_history,
    supersede_context_item,
)
from contextplane.database import build_engine
from contextplane.settings import Settings


def item(
    *,
    tenant_id: str = "acme",
    key: str = "security.pii.logging",
    domain: ContextDomain = ContextDomain.SECURITY,
    allowed: bool = False,
    checksum: str = "a" * 64,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"allowed": allowed},
        domain=domain,
        scope=ContextScope(tenant_id=tenant_id, environment="production"),
        owner="security-team",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum[:8]}",
        ),
        authority_level=AuthorityLevel.MANDATORY_CONTROL,
        effective_from=datetime(2026, 9, 28, tzinfo=UTC),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum,
    )


@pytest.mark.integration
def test_supersession_is_insert_only_and_history_is_ordered() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = create_context_item(session, item())
            first_id = first.id
            logical_id = first.logical_id
            original_checksum = first.checksum
            session.commit()

        with Session(engine) as session:
            second = supersede_context_item(
                session,
                tenant_id="acme",
                previous_id=first_id,
                replacement=item(allowed=True, checksum="b" * 64),
            )
            second_id = second.id
            session.commit()

        with Session(engine) as session:
            history = get_context_history(
                session,
                tenant_id="acme",
                logical_id=logical_id,
            )
            persisted_first = session.get(ContextItemRecord, first_id)

            assert [record.version for record in history] == [1, 2]
            assert history[0].id == first_id
            assert history[1].id == second_id
            assert history[1].supersedes_id == first_id
            assert history[1].logical_id == logical_id
            assert persisted_first is not None
            assert persisted_first.checksum == original_checksum
    finally:
        engine.dispose()


@pytest.mark.integration
def test_already_superseded_version_cannot_fork() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = create_context_item(session, item(checksum="c" * 64))
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            supersede_context_item(
                session,
                tenant_id="acme",
                previous_id=first_id,
                replacement=item(allowed=True, checksum="d" * 64),
            )
            session.commit()

        with Session(engine) as session:
            with pytest.raises(ContextVersionConflictError):
                supersede_context_item(
                    session,
                    tenant_id="acme",
                    previous_id=first_id,
                    replacement=item(allowed=False, checksum="e" * 64),
                )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_supersession_is_tenant_scoped() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = create_context_item(session, item(tenant_id="tenant-a", checksum="f" * 64))
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            with pytest.raises(ContextItemNotFoundError):
                supersede_context_item(
                    session,
                    tenant_id="tenant-b",
                    previous_id=first_id,
                    replacement=item(tenant_id="tenant-b", checksum="1" * 64),
                )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_replacement_cannot_change_logical_identity() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = create_context_item(session, item(checksum="2" * 64))
            first_id = first.id
            session.commit()

        with Session(engine) as session:
            with pytest.raises(ContextIdentityMismatchError):
                supersede_context_item(
                    session,
                    tenant_id="acme",
                    previous_id=first_id,
                    replacement=item(
                        key="security.other",
                        checksum="3" * 64,
                    ),
                )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_database_prevents_two_successors_for_one_version() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            first = create_context_item(session, item(checksum="4" * 64))
            first_id = first.id
            logical_id = first.logical_id
            session.commit()

        with Session(engine) as session:
            predecessor = session.get(ContextItemRecord, first_id)
            assert predecessor is not None

            common = {
                "key": predecessor.key,
                "value": {"allowed": True},
                "domain": predecessor.domain,
                "tenant_id": predecessor.tenant_id,
                "owner": predecessor.owner,
                "source_type": predecessor.source_type,
                "source_identifier": "manual-fork-test",
                "authority_level": predecessor.authority_level,
                "version": 2,
                "effective_from": predecessor.effective_from,
                "sensitivity": predecessor.sensitivity,
                "override_policy": predecessor.override_policy,
                "checksum": "5" * 64,
                "logical_id": logical_id,
                "supersedes_id": first_id,
            }
            session.add(ContextItemRecord(**common))
            session.add(
                ContextItemRecord(
                    **{**common, "id": None, "checksum": "6" * 64},
                )
            )

            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_history_never_crosses_tenant_boundary() -> None:
    engine = build_engine(Settings())

    try:
        with Session(engine) as session:
            record = create_context_item(session, item(tenant_id="history-a", checksum="7" * 64))
            logical_id = record.logical_id
            session.commit()

        with Session(engine) as session:
            assert get_context_history(
                session,
                tenant_id="history-b",
                logical_id=logical_id,
            ) == []

            rows = session.scalars(
                select(ContextItemRecord).where(
                    ContextItemRecord.logical_id == logical_id
                )
            ).all()
            assert len(rows) == 1
    finally:
        engine.dispose()

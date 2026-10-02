from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
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
from contextplane.context_registry.repository import create_context_item
from contextplane.database import build_engine
from contextplane.persistence.tenant import bind_session_tenant
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


def item(*, tenant_id: str, key: str, checksum_char: str) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": key},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(tenant_id=tenant_id),
        owner="rls-test",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"rls-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def test_rls_policies_exist_for_all_tenant_runtime_tables(engine) -> None:
    expected = {
        "context_items",
        "context_relations",
        "context_state_revisions",
        "resolution_audit",
        "publication_audit",
    }

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tablename
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND policyname LIKE '%_tenant_isolation'
                """
            )
        ).scalars()

    assert set(rows) == expected


def test_non_owner_role_cannot_read_across_bound_tenant(engine) -> None:
    tenant_a = f"rls-a-{uuid4()}"
    tenant_b = f"rls-b-{uuid4()}"
    role_name = f"contextplane_rls_{uuid4().hex}"

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_a,
                key="engineering.tenant-a",
                checksum_char="a",
            ),
        )
        create_context_item(
            session,
            item(
                tenant_id=tenant_b,
                key="engineering.tenant-b",
                checksum_char="b",
            ),
        )
        session.commit()

    with engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{role_name}" NOLOGIN'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role_name}"'))
        connection.execute(text(f'GRANT SELECT ON context_items TO "{role_name}"'))

    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection)
            session.execute(text(f'SET ROLE "{role_name}"'))

            bind_session_tenant(session, tenant_a)
            visible_a = set(
                session.scalars(select(ContextItemRecord.tenant_id)).all()
            )
            assert visible_a == {tenant_a}

            bind_session_tenant(session, tenant_b)
            visible_b = set(
                session.scalars(select(ContextItemRecord.tenant_id)).all()
            )
            assert visible_b == {tenant_b}

            session.execute(
                text("SELECT set_config('contextplane.tenant_id', '', true)")
            )
            assert session.scalars(select(ContextItemRecord.id)).all() == []

            session.close()
            transaction.rollback()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{role_name}"'))
            connection.execute(text(f'DROP ROLE IF EXISTS "{role_name}"'))


def test_non_owner_role_cannot_insert_foreign_tenant_state(engine) -> None:
    tenant_a = f"rls-write-a-{uuid4()}"
    tenant_b = f"rls-write-b-{uuid4()}"
    role_name = f"contextplane_rls_{uuid4().hex}"

    with engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{role_name}" NOLOGIN'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role_name}"'))
        connection.execute(
            text(
                f'GRANT SELECT, INSERT ON context_state_revisions TO "{role_name}"'
            )
        )

    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection)
            session.execute(text(f'SET ROLE "{role_name}"'))
            bind_session_tenant(session, tenant_a)

            with pytest.raises(DBAPIError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO context_state_revisions (tenant_id, revision)
                        VALUES (:tenant_id, 0)
                        """
                    ),
                    {"tenant_id": tenant_b},
                )
                session.flush()

            session.close()
            transaction.rollback()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{role_name}"'))
            connection.execute(text(f'DROP ROLE IF EXISTS "{role_name}"'))

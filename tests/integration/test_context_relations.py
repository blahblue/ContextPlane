from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contextplane.context_graph import (
    ContextRelationConflictError,
    ContextRelationCreate,
    ContextRelationEndpointNotFoundError,
    RelationType,
    create_context_relation,
    get_incoming_relations,
    get_outgoing_relations,
)
from contextplane.context_graph.db import ContextRelationRecord
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
from contextplane.settings import Settings


def item(
    *,
    tenant_id: str,
    key: str,
    domain: ContextDomain,
    checksum: str,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"enabled": True},
        domain=domain,
        scope=ContextScope(tenant_id=tenant_id),
        owner="graph-test",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum[:8]}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=datetime(2026, 9, 28, tzinfo=UTC),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum,
    )


def create_pair(session: Session, tenant_id: str) -> tuple[UUID, UUID, UUID, UUID]:
    source = create_context_item(
        session,
        item(
            tenant_id=tenant_id,
            key="engineering.api.versioning",
            domain=ContextDomain.ENGINEERING,
            checksum="a" * 64,
        ),
    )
    target = create_context_item(
        session,
        item(
            tenant_id=tenant_id,
            key="security.pii.logging",
            domain=ContextDomain.SECURITY,
            checksum="b" * 64,
        ),
    )
    return source.logical_id, source.id, target.logical_id, target.id


@pytest.mark.integration
def test_create_and_query_typed_relation() -> None:
    engine = build_engine(Settings())
    tenant_id = f"graph-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, _, target_logical, _ = create_pair(session, tenant_id)
            relation = create_context_relation(
                session,
                ContextRelationCreate(
                    tenant_id=tenant_id,
                    source_logical_id=source_logical,
                    target_logical_id=target_logical,
                    relation_type=RelationType.GOVERNS,
                ),
            )
            session.commit()
            relation_id = relation.id

        with Session(engine) as session:
            outgoing = get_outgoing_relations(
                session,
                tenant_id=tenant_id,
                source_logical_id=source_logical,
            )
            incoming = get_incoming_relations(
                session,
                tenant_id=tenant_id,
                target_logical_id=target_logical,
                relation_type=RelationType.GOVERNS,
            )

            assert [edge.id for edge in outgoing] == [relation_id]
            assert [edge.id for edge in incoming] == [relation_id]
            assert outgoing[0].relation_type == "governs"
    finally:
        engine.dispose()


@pytest.mark.integration
def test_relation_survives_context_supersession() -> None:
    engine = build_engine(Settings())
    tenant_id = f"graph-version-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, source_anchor, target_logical, _ = create_pair(session, tenant_id)
            relation = create_context_relation(
                session,
                ContextRelationCreate(
                    tenant_id=tenant_id,
                    source_logical_id=source_logical,
                    target_logical_id=target_logical,
                    relation_type=RelationType.DEPENDS_ON,
                ),
            )
            relation_id = relation.id
            session.commit()

        with Session(engine) as session:
            supersede_context_item(
                session,
                tenant_id=tenant_id,
                previous_id=source_anchor,
                replacement=item(
                    tenant_id=tenant_id,
                    key="engineering.api.versioning",
                    domain=ContextDomain.ENGINEERING,
                    checksum="c" * 64,
                ),
            )
            session.commit()

        with Session(engine) as session:
            edge = session.get(ContextRelationRecord, relation_id)
            outgoing = get_outgoing_relations(
                session,
                tenant_id=tenant_id,
                source_logical_id=source_logical,
            )

            assert edge is not None
            assert edge.source_anchor_id == source_anchor
            assert [record.id for record in outgoing] == [relation_id]
    finally:
        engine.dispose()


@pytest.mark.integration
def test_relation_creation_does_not_cross_tenants() -> None:
    engine = build_engine(Settings())
    tenant_a = f"graph-a-{uuid4()}"
    tenant_b = f"graph-b-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, _, _, _ = create_pair(session, tenant_a)
            _, _, target_logical, _ = create_pair(session, tenant_b)
            session.commit()

        with Session(engine) as session, pytest.raises(ContextRelationEndpointNotFoundError):
            create_context_relation(
                session,
                ContextRelationCreate(
                    tenant_id=tenant_a,
                    source_logical_id=source_logical,
                    target_logical_id=target_logical,
                    relation_type=RelationType.USES,
                ),
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_duplicate_logical_edge_is_rejected() -> None:
    engine = build_engine(Settings())
    tenant_id = f"graph-duplicate-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, _, target_logical, _ = create_pair(session, tenant_id)
            relation = ContextRelationCreate(
                tenant_id=tenant_id,
                source_logical_id=source_logical,
                target_logical_id=target_logical,
                relation_type=RelationType.RELATED_TO,
            )
            create_context_relation(session, relation)
            session.commit()

        with Session(engine) as session, pytest.raises(ContextRelationConflictError):
            create_context_relation(session, relation)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_database_rejects_cross_tenant_target_anchor() -> None:
    engine = build_engine(Settings())
    tenant_a = f"graph-direct-a-{uuid4()}"
    tenant_b = f"graph-direct-b-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, source_id, _, _ = create_pair(session, tenant_a)
            _, _, target_logical, target_id = create_pair(session, tenant_b)
            session.commit()

        with Session(engine) as session:
            session.add(
                ContextRelationRecord(
                    tenant_id=tenant_a,
                    source_logical_id=source_logical,
                    source_anchor_id=source_id,
                    target_logical_id=target_logical,
                    target_anchor_id=target_id,
                    relation_type="governs",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("relation_type", ["invented", ""])
def test_database_rejects_invalid_relation_type(relation_type: str) -> None:
    engine = build_engine(Settings())
    tenant_id = f"graph-type-{uuid4()}"

    try:
        with Session(engine) as session:
            source_logical, source_id, target_logical, target_id = create_pair(
                session,
                tenant_id,
            )
            session.add(
                ContextRelationRecord(
                    tenant_id=tenant_id,
                    source_logical_id=source_logical,
                    source_anchor_id=source_id,
                    target_logical_id=target_logical,
                    target_anchor_id=target_id,
                    relation_type=relation_type,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()

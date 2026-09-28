"""Tenant-scoped persistence operations for context graph relations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.context_graph.db import ContextRelationRecord
from contextplane.context_graph.domain import ContextRelationCreate, RelationType
from contextplane.context_registry.db import ContextItemRecord


class ContextRelationEndpointNotFoundError(LookupError):
    """Raised when either endpoint is not visible inside the requested tenant."""


class ContextRelationConflictError(RuntimeError):
    """Raised when a logical edge already exists."""


def _latest_anchor(
    session: Session,
    *,
    tenant_id: str,
    logical_id: UUID,
) -> ContextItemRecord:
    """Resolve one logical identity to its latest immutable version in a tenant."""
    anchor = session.scalar(
        select(ContextItemRecord)
        .where(
            ContextItemRecord.tenant_id == tenant_id,
            ContextItemRecord.logical_id == logical_id,
        )
        .order_by(ContextItemRecord.version.desc())
        .limit(1)
    )
    if anchor is None:
        raise ContextRelationEndpointNotFoundError(
            "one or more relation endpoints were not found in the requested tenant"
        )
    return anchor


def create_context_relation(
    session: Session,
    relation: ContextRelationCreate,
) -> ContextRelationRecord:
    """Create one directed edge between logical context identities."""
    source = _latest_anchor(
        session,
        tenant_id=relation.tenant_id,
        logical_id=relation.source_logical_id,
    )
    target = _latest_anchor(
        session,
        tenant_id=relation.tenant_id,
        logical_id=relation.target_logical_id,
    )

    existing = session.scalar(
        select(ContextRelationRecord.id).where(
            ContextRelationRecord.tenant_id == relation.tenant_id,
            ContextRelationRecord.source_logical_id == relation.source_logical_id,
            ContextRelationRecord.target_logical_id == relation.target_logical_id,
            ContextRelationRecord.relation_type == relation.relation_type.value,
        )
    )
    if existing is not None:
        raise ContextRelationConflictError("context relation already exists")

    record = ContextRelationRecord(
        tenant_id=relation.tenant_id,
        source_logical_id=relation.source_logical_id,
        source_anchor_id=source.id,
        target_logical_id=relation.target_logical_id,
        target_anchor_id=target.id,
        relation_type=relation.relation_type.value,
    )
    session.add(record)
    session.flush()
    return record


def get_outgoing_relations(
    session: Session,
    *,
    tenant_id: str,
    source_logical_id: UUID,
    relation_type: RelationType | None = None,
) -> list[ContextRelationRecord]:
    """Return tenant-scoped outgoing edges in deterministic order."""
    query = select(ContextRelationRecord).where(
        ContextRelationRecord.tenant_id == tenant_id,
        ContextRelationRecord.source_logical_id == source_logical_id,
    )
    if relation_type is not None:
        query = query.where(ContextRelationRecord.relation_type == relation_type.value)

    return list(
        session.scalars(
            query.order_by(
                ContextRelationRecord.relation_type.asc(),
                ContextRelationRecord.target_logical_id.asc(),
            )
        )
    )


def get_incoming_relations(
    session: Session,
    *,
    tenant_id: str,
    target_logical_id: UUID,
    relation_type: RelationType | None = None,
) -> list[ContextRelationRecord]:
    """Return tenant-scoped incoming edges in deterministic order."""
    query = select(ContextRelationRecord).where(
        ContextRelationRecord.tenant_id == tenant_id,
        ContextRelationRecord.target_logical_id == target_logical_id,
    )
    if relation_type is not None:
        query = query.where(ContextRelationRecord.relation_type == relation_type.value)

    return list(
        session.scalars(
            query.order_by(
                ContextRelationRecord.relation_type.asc(),
                ContextRelationRecord.source_logical_id.asc(),
            )
        )
    )

"""SQLAlchemy persistence model for typed context graph relations."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class ContextRelationRecord(Base):
    """Directed relation between two logical context identities."""

    __tablename__ = "context_relations"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_relations_tenant_nonempty",
        ),
        CheckConstraint(
            "source_logical_id <> target_logical_id",
            name="ck_context_relations_no_self_edge",
        ),
        CheckConstraint(
            "relation_type IN ('belongs_to','depends_on','governs','related_to','uses')",
            name="ck_context_relations_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_logical_id",
            "relation_type",
            "target_logical_id",
            name="uq_context_relations_logical_edge",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_logical_id", "source_anchor_id"],
            [
                "context_items.tenant_id",
                "context_items.logical_id",
                "context_items.id",
            ],
            name="fk_context_relations_source_same_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_logical_id", "target_anchor_id"],
            [
                "context_items.tenant_id",
                "context_items.logical_id",
                "context_items.id",
            ],
            name="fk_context_relations_target_same_tenant",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_context_relations_outgoing",
            "tenant_id",
            "source_logical_id",
            "relation_type",
        ),
        Index(
            "ix_context_relations_incoming",
            "tenant_id",
            "target_logical_id",
            "relation_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_logical_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_anchor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_logical_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_anchor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

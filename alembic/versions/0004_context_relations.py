"""Create tenant-scoped typed context relations.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create logical context graph edges with tenant-bound endpoint anchors."""
    op.create_table(
        "context_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=512), nullable=False),
        sa.Column("source_logical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_anchor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_logical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_anchor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_relations_tenant_nonempty",
        ),
        sa.CheckConstraint(
            "source_logical_id <> target_logical_id",
            name="ck_context_relations_no_self_edge",
        ),
        sa.CheckConstraint(
            "relation_type IN ('belongs_to','depends_on','governs','related_to','uses')",
            name="ck_context_relations_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_logical_id", "source_anchor_id"],
            ["context_items.tenant_id", "context_items.logical_id", "context_items.id"],
            name="fk_context_relations_source_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_logical_id", "target_anchor_id"],
            ["context_items.tenant_id", "context_items.logical_id", "context_items.id"],
            name="fk_context_relations_target_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_logical_id",
            "relation_type",
            "target_logical_id",
            name="uq_context_relations_logical_edge",
        ),
    )
    op.create_index(
        "ix_context_relations_outgoing",
        "context_relations",
        ["tenant_id", "source_logical_id", "relation_type"],
        unique=False,
    )
    op.create_index(
        "ix_context_relations_incoming",
        "context_relations",
        ["tenant_id", "target_logical_id", "relation_type"],
        unique=False,
    )


def downgrade() -> None:
    """Remove context graph relations."""
    op.drop_index("ix_context_relations_incoming", table_name="context_relations")
    op.drop_index("ix_context_relations_outgoing", table_name="context_relations")
    op.drop_table("context_relations")

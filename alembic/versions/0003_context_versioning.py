"""Add immutable logical versioning and supersession links.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add logical identity and append-only supersession metadata."""
    op.add_column(
        "context_items",
        sa.Column("logical_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "context_items",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Existing version-1 records become the root of their own logical histories.
    op.execute("UPDATE context_items SET logical_id = id WHERE logical_id IS NULL")
    op.alter_column("context_items", "logical_id", nullable=False)

    op.create_unique_constraint(
        "uq_context_items_tenant_logical_id",
        "context_items",
        ["tenant_id", "logical_id", "id"],
    )
    op.create_foreign_key(
        "fk_context_items_supersedes_same_logical_item",
        "context_items",
        "context_items",
        ["tenant_id", "logical_id", "supersedes_id"],
        ["tenant_id", "logical_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_context_items_no_self_supersession",
        "context_items",
        "supersedes_id IS NULL OR supersedes_id <> id",
    )
    op.create_check_constraint(
        "ck_context_items_version_lineage_shape",
        "context_items",
        "(version = 1 AND supersedes_id IS NULL) OR "
        "(version > 1 AND supersedes_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_context_items_tenant_logical_version",
        "context_items",
        ["tenant_id", "logical_id", "version"],
    )
    op.create_unique_constraint(
        "uq_context_items_supersedes_id",
        "context_items",
        ["supersedes_id"],
    )
    op.create_index(
        "ix_context_items_tenant_logical",
        "context_items",
        ["tenant_id", "logical_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove logical versioning metadata."""
    op.drop_index("ix_context_items_tenant_logical", table_name="context_items")
    op.drop_constraint(
        "uq_context_items_supersedes_id",
        "context_items",
        type_="unique",
    )
    op.drop_constraint(
        "uq_context_items_tenant_logical_version",
        "context_items",
        type_="unique",
    )
    op.drop_constraint(
        "ck_context_items_version_lineage_shape",
        "context_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_context_items_no_self_supersession",
        "context_items",
        type_="check",
    )
    op.drop_constraint(
        "fk_context_items_supersedes_same_logical_item",
        "context_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_context_items_tenant_logical_id",
        "context_items",
        type_="unique",
    )
    op.drop_column("context_items", "supersedes_id")
    op.drop_column("context_items", "logical_id")

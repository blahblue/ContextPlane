"""Create the context_items table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the initial governed context schema."""
    op.create_table(
        "context_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("payload_ref", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=512), nullable=False),
        sa.Column("business_unit", sa.String(length=512), nullable=True),
        sa.Column("team", sa.String(length=512), nullable=True),
        sa.Column("role", sa.String(length=512), nullable=True),
        sa.Column("user_id", sa.String(length=512), nullable=True),
        sa.Column("agent_id", sa.String(length=512), nullable=True),
        sa.Column("application", sa.String(length=512), nullable=True),
        sa.Column("repository", sa.String(length=512), nullable=True),
        sa.Column("resource", sa.String(length=512), nullable=True),
        sa.Column("task", sa.String(length=512), nullable=True),
        sa.Column("audience", sa.String(length=512), nullable=True),
        sa.Column("environment", sa.String(length=512), nullable=True),
        sa.Column("owner", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_identifier", sa.String(length=512), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("authority_level", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sensitivity", sa.String(length=64), nullable=False),
        sa.Column("override_policy", sa.String(length=64), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "authority_level IN "
            "('preference','recommendation','standard','policy','mandatory_control')",
            name="ck_context_items_authority",
        ),
        sa.CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_context_items_checksum_sha256",
        ),
        sa.CheckConstraint(
            "domain IN ('brand','presentation','engineering','security')",
            name="ck_context_items_domain",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_context_items_effective_window",
        ),
        sa.CheckConstraint(
            "(value IS NOT NULL) <> (payload_ref IS NOT NULL)",
            name="ck_context_items_exactly_one_payload",
        ),
        sa.CheckConstraint(
            "length(btrim(key)) > 0",
            name="ck_context_items_key_nonempty",
        ),
        sa.CheckConstraint(
            "length(btrim(owner)) > 0",
            name="ck_context_items_owner_nonempty",
        ),
        sa.CheckConstraint(
            "override_policy IN ('allow','deny')",
            name="ck_context_items_override_policy",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('public','internal','confidential','restricted')",
            name="ck_context_items_sensitivity",
        ),
        sa.CheckConstraint(
            "length(btrim(source_identifier)) > 0",
            name="ck_context_items_source_identifier_nonempty",
        ),
        sa.CheckConstraint(
            "source_type IN "
            "('manual','git','sharepoint','google_drive','databricks','fabric','api')",
            name="ck_context_items_source_type",
        ),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_items_tenant_nonempty",
        ),
        sa.CheckConstraint("version > 0", name="ck_context_items_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_items_tenant_id",
        "context_items",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_context_items_tenant_key",
        "context_items",
        ["tenant_id", "key"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the initial governed context schema."""
    op.drop_index("ix_context_items_tenant_key", table_name="context_items")
    op.drop_index("ix_context_items_tenant_id", table_name="context_items")
    op.drop_table("context_items")

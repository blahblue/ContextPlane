"""Create immutable context resolution audit log.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create append-only resolution audit storage and mutation guard."""
    op.create_table(
        "resolution_audit",
        sa.Column("resolution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=512), nullable=False),
        sa.Column("principal_kind", sa.String(length=32), nullable=False),
        sa.Column("principal_subject", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=512), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_domains", postgresql.JSONB(), nullable=False),
        sa.Column("requested_key_hashes", postgresql.JSONB(), nullable=False),
        sa.Column("selector_hashes", postgresql.JSONB(), nullable=False),
        sa.Column("policy_decision", sa.String(length=32), nullable=True),
        sa.Column("allowed_domains", postgresql.JSONB(), nullable=False),
        sa.Column("denied_domains", postgresql.JSONB(), nullable=False),
        sa.Column("policy_rule_ids", postgresql.JSONB(), nullable=False),
        sa.Column("considered_record_ids", postgresql.JSONB(), nullable=False),
        sa.Column("returned_items", postgresql.JSONB(), nullable=False),
        sa.Column("conflict_steps", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_resolution_audit_tenant_nonempty",
        ),
        sa.CheckConstraint(
            "length(btrim(principal_subject)) > 0",
            name="ck_resolution_audit_subject_nonempty",
        ),
        sa.CheckConstraint(
            "principal_kind IN ('user','agent','service')",
            name="ck_resolution_audit_principal_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('allowed','narrowed','denied','conflict','policy_error')",
            name="ck_resolution_audit_outcome",
        ),
        sa.PrimaryKeyConstraint("resolution_id"),
    )
    op.create_index(
        "ix_resolution_audit_tenant_id",
        "resolution_audit",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_audit_tenant_created",
        "resolution_audit",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION contextplane_reject_resolution_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'resolution audit records are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_resolution_audit_immutable
        BEFORE UPDATE OR DELETE ON resolution_audit
        FOR EACH ROW
        EXECUTE FUNCTION contextplane_reject_resolution_audit_mutation();
        """
    )


def downgrade() -> None:
    """Remove audit storage and its mutation guard."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_resolution_audit_immutable ON resolution_audit"
    )
    op.drop_index("ix_resolution_audit_tenant_created", table_name="resolution_audit")
    op.drop_index("ix_resolution_audit_tenant_id", table_name="resolution_audit")
    op.drop_table("resolution_audit")
    op.execute(
        "DROP FUNCTION IF EXISTS contextplane_reject_resolution_audit_mutation()"
    )

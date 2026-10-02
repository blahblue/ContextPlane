"""Add authenticated publication provenance and audit.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("context_items", sa.Column("publisher_subject", sa.String(512), nullable=True))
    op.add_column("context_items", sa.Column("publisher_kind", sa.String(32), nullable=True))
    op.add_column("context_items", sa.Column("publisher_client_id", sa.String(512), nullable=True))
    op.add_column("context_items", sa.Column("publication_action", sa.String(32), nullable=True))
    op.add_column("context_items", sa.Column("publication_permission", sa.String(128), nullable=True))
    op.create_check_constraint(
        "ck_context_items_publication_provenance_shape",
        "context_items",
        """
        (
          publisher_subject IS NULL
          AND publisher_kind IS NULL
          AND publication_action IS NULL
          AND publication_permission IS NULL
        )
        OR
        (
          publisher_subject IS NOT NULL
          AND publisher_kind IN ('user','agent','service')
          AND publication_action IN ('create','supersede')
          AND publication_permission IS NOT NULL
        )
        """,
    )

    op.create_table(
        "publication_audit",
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(512), nullable=False),
        sa.Column("principal_kind", sa.String(32), nullable=False),
        sa.Column("principal_subject", sa.String(512), nullable=False),
        sa.Column("client_id", sa.String(512), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("authority_level", sa.String(64), nullable=False),
        sa.Column("permission_used", sa.String(128), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("previous_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("logical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("publication_id"),
        sa.CheckConstraint("length(btrim(tenant_id)) > 0", name="ck_publication_audit_tenant"),
        sa.CheckConstraint("length(btrim(principal_subject)) > 0", name="ck_publication_audit_subject"),
        sa.CheckConstraint("principal_kind IN ('user','agent','service')", name="ck_publication_audit_principal_kind"),
        sa.CheckConstraint("action IN ('create','supersede')", name="ck_publication_audit_action"),
        sa.CheckConstraint("authority_level IN ('preference','recommendation','standard','policy','mandatory_control')", name="ck_publication_audit_authority"),
        sa.CheckConstraint("outcome IN ('succeeded','denied','conflict')", name="ck_publication_audit_outcome"),
        sa.CheckConstraint("idempotency_key_hash ~ '^[0-9a-f]{64}$'", name="ck_publication_audit_idempotency_hash"),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_publication_audit_request_hash"),
        sa.CheckConstraint("key_hash ~ '^[0-9a-f]{64}$'", name="ck_publication_audit_key_hash"),
    )
    op.create_index("ix_publication_audit_tenant", "publication_audit", ["tenant_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_publication_audit_actor_idempotency
        ON publication_audit (
            tenant_id,
            principal_kind,
            principal_subject,
            COALESCE(client_id, ''),
            idempotency_key_hash
        )
        """
    )
    op.execute("ALTER TABLE publication_audit ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY publication_audit_tenant_isolation
        ON publication_audit
        USING (
            tenant_id = NULLIF(current_setting('contextplane.tenant_id', true), '')
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('contextplane.tenant_id', true), '')
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION contextplane_reject_publication_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'publication audit records are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_publication_audit_immutable
        BEFORE UPDATE OR DELETE ON publication_audit
        FOR EACH ROW
        EXECUTE FUNCTION contextplane_reject_publication_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_publication_audit_immutable ON publication_audit")
    op.execute("DROP FUNCTION IF EXISTS contextplane_reject_publication_audit_mutation()")
    op.execute("DROP POLICY IF EXISTS publication_audit_tenant_isolation ON publication_audit")
    op.execute("ALTER TABLE publication_audit DISABLE ROW LEVEL SECURITY")
    op.drop_index("uq_publication_audit_actor_idempotency", table_name="publication_audit")
    op.drop_index("ix_publication_audit_tenant", table_name="publication_audit")
    op.drop_table("publication_audit")
    op.drop_constraint("ck_context_items_publication_provenance_shape", "context_items", type_="check")
    for column in (
        "publication_permission",
        "publication_action",
        "publisher_client_id",
        "publisher_kind",
        "publisher_subject",
    ):
        op.drop_column("context_items", column)

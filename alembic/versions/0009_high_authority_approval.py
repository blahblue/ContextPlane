"""Add immutable high-authority publication approval workflow.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create proposal and approval-event persistence."""
    op.create_table(
        "publication_proposals",
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(512), nullable=False),
        sa.Column("publisher_kind", sa.String(32), nullable=False),
        sa.Column("publisher_subject", sa.String(512), nullable=False),
        sa.Column("publisher_client_id", sa.String(512), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("authority_level", sa.String(64), nullable=False),
        sa.Column("publication_permission", sa.String(128), nullable=False),
        sa.Column(
            "previous_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("item_payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "proposal_id",
            name="uq_publication_proposals_tenant_id",
        ),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_publication_proposals_tenant",
        ),
        sa.CheckConstraint(
            "length(btrim(publisher_subject)) > 0",
            name="ck_publication_proposals_subject",
        ),
        sa.CheckConstraint(
            "publisher_kind IN ('user','agent','service')",
            name="ck_publication_proposals_kind",
        ),
        sa.CheckConstraint(
            "action IN ('create','supersede')",
            name="ck_publication_proposals_action",
        ),
        sa.CheckConstraint(
            "authority_level IN ('policy','mandatory_control')",
            name="ck_publication_proposals_authority",
        ),
        sa.CheckConstraint(
            "publication_permission IN "
            "('context.publish.policy','context.publish.mandatory_control')",
            name="ck_publication_proposals_permission",
        ),
        sa.CheckConstraint(
            "(action = 'create' AND previous_record_id IS NULL) OR "
            "(action = 'supersede' AND previous_record_id IS NOT NULL)",
            name="ck_publication_proposals_previous_shape",
        ),
        sa.CheckConstraint(
            "idempotency_key_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_proposals_idempotency_hash",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_proposals_request_hash",
        ),
    )
    op.create_index(
        "ix_publication_proposals_tenant_id",
        "publication_proposals",
        ["tenant_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_publication_proposals_actor_idempotency
        ON publication_proposals (
            tenant_id,
            publisher_kind,
            publisher_subject,
            COALESCE(publisher_client_id, ''),
            idempotency_key_hash
        )
        """
    )

    op.create_table(
        "publication_approval_events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(512), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_kind", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(512), nullable=False),
        sa.Column("actor_client_id", sa.String(512), nullable=True),
        sa.Column("permission_used", sa.String(128), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "context_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("logical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            [
                "publication_proposals.tenant_id",
                "publication_proposals.proposal_id",
            ],
            name="fk_publication_approval_events_tenant_proposal",
        ),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_publication_approval_events_tenant",
        ),
        sa.CheckConstraint(
            "length(btrim(actor_subject)) > 0",
            name="ck_publication_approval_events_subject",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('user','agent','service')",
            name="ck_publication_approval_events_kind",
        ),
        sa.CheckConstraint(
            "event_type IN ('approve','activate')",
            name="ck_publication_approval_events_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded','denied','conflict')",
            name="ck_publication_approval_events_outcome",
        ),
        sa.CheckConstraint(
            "permission_used IS NULL OR permission_used IN ("
            "'context.approve.policy',"
            "'context.approve.mandatory_control',"
            "'context.activate.policy',"
            "'context.activate.mandatory_control'"
            ")",
            name="ck_publication_approval_events_permission",
        ),
        sa.CheckConstraint(
            "("
            "event_type = 'approve' AND context_record_id IS NULL "
            "AND logical_id IS NULL AND version IS NULL"
            ") OR event_type = 'activate'",
            name="ck_publication_approval_events_type_shape",
        ),
        sa.CheckConstraint(
            "("
            "event_type = 'activate' AND outcome = 'succeeded' "
            "AND context_record_id IS NOT NULL AND logical_id IS NOT NULL "
            "AND version IS NOT NULL AND version > 0 AND error_code IS NULL"
            ") OR ("
            "event_type = 'approve' AND outcome = 'succeeded' "
            "AND error_code IS NULL"
            ") OR ("
            "outcome IN ('denied','conflict') AND error_code IS NOT NULL "
            "AND context_record_id IS NULL AND logical_id IS NULL "
            "AND version IS NULL"
            ")",
            name="ck_publication_approval_events_outcome_shape",
        ),
    )
    op.create_index(
        "ix_publication_approval_events_tenant_id",
        "publication_approval_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_publication_approval_events_proposal_id",
        "publication_approval_events",
        ["proposal_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_publication_approval_success
        ON publication_approval_events (tenant_id, proposal_id, event_type)
        WHERE outcome = 'succeeded'
        """
    )

    for table in ("publication_proposals", "publication_approval_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            USING (
                tenant_id = NULLIF(
                    current_setting('contextplane.tenant_id', true),
                    ''
                )
            )
            WITH CHECK (
                tenant_id = NULLIF(
                    current_setting('contextplane.tenant_id', true),
                    ''
                )
            )
            """
        )

    op.execute(
        """
        CREATE FUNCTION contextplane_reject_approval_workflow_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'publication approval workflow records are immutable';
        END;
        $$
        """
    )
    for table in ("publication_proposals", "publication_approval_events"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION contextplane_reject_approval_workflow_mutation()
            """
        )


def downgrade() -> None:
    """Remove high-authority approval workflow persistence."""
    for table in ("publication_approval_events", "publication_proposals"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "contextplane_reject_approval_workflow_mutation()"
    )

    for table in ("publication_approval_events", "publication_proposals"):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "uq_publication_approval_success",
        table_name="publication_approval_events",
    )
    op.drop_index(
        "ix_publication_approval_events_proposal_id",
        table_name="publication_approval_events",
    )
    op.drop_index(
        "ix_publication_approval_events_tenant_id",
        table_name="publication_approval_events",
    )
    op.drop_table("publication_approval_events")

    op.drop_index(
        "uq_publication_proposals_actor_idempotency",
        table_name="publication_proposals",
    )
    op.drop_index(
        "ix_publication_proposals_tenant_id",
        table_name="publication_proposals",
    )
    op.drop_table("publication_proposals")

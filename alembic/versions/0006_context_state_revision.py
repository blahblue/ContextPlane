"""Add monotonic tenant context revision state.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create revision state and bump it on every context-item mutation."""
    op.create_table(
        "context_state_revisions",
        sa.Column("tenant_id", sa.String(length=512), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_state_revision_tenant_nonempty",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_context_state_revision_nonnegative",
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    op.execute(
        """
        INSERT INTO context_state_revisions (tenant_id, revision)
        SELECT tenant_id, COUNT(*)::bigint
        FROM context_items
        GROUP BY tenant_id
        """
    )

    op.execute(
        """
        CREATE FUNCTION contextplane_bump_context_revision()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            affected_tenant text;
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD.tenant_id IS DISTINCT FROM NEW.tenant_id THEN
                INSERT INTO context_state_revisions (tenant_id, revision)
                VALUES (OLD.tenant_id, 1)
                ON CONFLICT (tenant_id)
                DO UPDATE SET revision = context_state_revisions.revision + 1;

                INSERT INTO context_state_revisions (tenant_id, revision)
                VALUES (NEW.tenant_id, 1)
                ON CONFLICT (tenant_id)
                DO UPDATE SET revision = context_state_revisions.revision + 1;

                RETURN NEW;
            END IF;

            affected_tenant := CASE
                WHEN TG_OP = 'DELETE' THEN OLD.tenant_id
                ELSE NEW.tenant_id
            END;

            INSERT INTO context_state_revisions (tenant_id, revision)
            VALUES (affected_tenant, 1)
            ON CONFLICT (tenant_id)
            DO UPDATE SET revision = context_state_revisions.revision + 1;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_context_items_revision
        AFTER INSERT OR UPDATE OR DELETE ON context_items
        FOR EACH ROW
        EXECUTE FUNCTION contextplane_bump_context_revision();
        """
    )


def downgrade() -> None:
    """Remove context revision state and trigger."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_context_items_revision ON context_items"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS contextplane_bump_context_revision()"
    )
    op.drop_table("context_state_revisions")

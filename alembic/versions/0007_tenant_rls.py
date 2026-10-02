"""Enable tenant-aware PostgreSQL row-level security policies.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02
"""

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

_TABLES = (
    "context_items",
    "context_relations",
    "context_state_revisions",
    "resolution_audit",
)


def upgrade() -> None:
    """Add deny-by-default tenant policies for non-owner runtime roles."""
    for table in _TABLES:
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


def downgrade() -> None:
    """Remove tenant RLS policies."""
    for table in reversed(_TABLES):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

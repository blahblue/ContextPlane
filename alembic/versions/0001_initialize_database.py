"""Initialize the ContextPlane database.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Establish the initial migration boundary."""
    pass


def downgrade() -> None:
    """Remove the initial migration boundary."""
    pass

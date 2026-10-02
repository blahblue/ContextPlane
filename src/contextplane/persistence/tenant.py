"""PostgreSQL tenant session binding used by runtime RLS policies."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def bind_session_tenant(session: Session, tenant_id: str) -> None:
    """Bind the authenticated tenant to the current database transaction."""
    if not tenant_id.strip():
        raise ValueError("tenant_id must be non-empty")

    session.execute(
        text("SELECT set_config('contextplane.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )

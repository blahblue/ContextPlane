"""Database engine helpers."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from contextplane.settings import Settings


def build_engine(settings: Settings | None = None) -> Engine:
    """Create a SQLAlchemy engine from explicit runtime settings."""
    resolved = settings or Settings()
    return create_engine(
        resolved.database_url,
        pool_pre_ping=True,
    )


def database_ready(engine: Engine) -> bool:
    """Verify that the database accepts a minimal read-only query."""
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1

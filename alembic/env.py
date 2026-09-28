"""Alembic migration environment."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from contextplane.audit.db import ResolutionAuditRecord
from contextplane.context_graph.db import ContextRelationRecord
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.state_db import ContextStateRevisionRecord
from contextplane.settings import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = ContextItemRecord.metadata
if (
    ContextRelationRecord.metadata is not target_metadata
    or ResolutionAuditRecord.metadata is not target_metadata
    or ContextStateRevisionRecord.metadata is not target_metadata
):
    raise RuntimeError("ContextPlane persistence models must share SQLAlchemy metadata")


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

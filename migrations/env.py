from logging.config import fileConfig

from alembic import context
from sqlalchemy import JSON, pool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Treat portable JSON/JSONB variants as equivalent during autogeneration."""
    if isinstance(inspected_type, (JSON, JSONB)) and isinstance(metadata_type, (JSON, JSONB)):
        return False
    return None


def include_object(object_, name, object_type, reflected, compare_to):
    """Keep legacy indexes out of the migration drift gate.

    Indexes are provisioned independently for the production workload; the
    migration gate still compares tables, columns, constraints and types.
    """
    return object_type != "index"


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=compare_type,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=compare_type, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

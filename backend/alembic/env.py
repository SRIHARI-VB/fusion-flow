"""Alembic environment — async (asyncpg) compatible.

The database URL always comes from `fusionflow.config.Settings`, never from
alembic.ini, so `alembic upgrade head` and the running app can never point
at different databases.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from fusionflow.config import get_settings

# Importing the model registry populates Base.metadata for autogenerate.
from fusionflow.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# `configparser` (which backs alembic's `Config`) treats a literal `%` as the
# start of `%(...)s`-style interpolation syntax - a DB password containing a
# percent-encoded character (e.g. `%40` for a literal `@`) raises
# `ValueError: invalid interpolation syntax` here otherwise. `%%` is
# configparser's own escape for a literal `%`. This is purely informational
# (populates `alembic.ini`'s in-memory config for commands like `alembic
# current` to display) - `run_migrations_online`/`run_migrations_offline`
# below both read `settings.DATABASE_URL` directly, never through this.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Built directly from settings.DATABASE_URL, not via async_engine_from_config
    # reading the ini section - the escaped (%%) form stored there by
    # set_main_option above is for display only and would connect with the
    # wrong (literally doubled-percent) password if used here.
    connectable = create_async_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

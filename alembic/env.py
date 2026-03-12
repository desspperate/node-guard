import asyncio
from logging.config import fileConfig
from dotenv import load_dotenv

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from heartbeat_monitor.enums import EnvironmentEnum

load_dotenv()

import heartbeat_monitor.models  # noqa: F401
from heartbeat_monitor.database import PureBase
from heartbeat_monitor.config import PostgresConfig, heartbeat_monitor_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

in_docker = heartbeat_monitor_config.ENV == EnvironmentEnum.DOCKER
postgres_config = PostgresConfig()  # type: ignore[call-args]

config.set_main_option(
    name="sqlalchemy.url",
    value=f"{postgres_config.PG_DRIVER}://"
          f"{postgres_config.PG_USER}:"
          f"{postgres_config.PG_PASSWORD.get_secret_value()}@"
          f"{postgres_config.PG_HOST if in_docker else "localhost"}:"
          f"{postgres_config.PG_PORT if in_docker else "5433"}/"
          f"heartbeat_monitor_database",
)
target_metadata = PureBase.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

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
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

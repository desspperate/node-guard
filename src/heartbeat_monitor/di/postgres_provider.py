from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide  # type: ignore[reportUnknownVariableType]
from loguru import logger
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from heartbeat_monitor.config import PostgresConfig


class PostgresProvider(Provider):
    @provide(scope=Scope.APP)
    def get_pg_config(self) -> PostgresConfig:
        return PostgresConfig()  # type: ignore[call-args]

    @provide(scope=Scope.APP)
    def get_postgres_url(self, pg_config: PostgresConfig) -> URL:
        return URL.create(
            drivername=pg_config.PG_DRIVER,
            host=pg_config.PG_HOST,
            port=pg_config.PG_PORT,
            username=pg_config.PG_USER,
            password=pg_config.PG_PASSWORD.get_secret_value(),
            database=pg_config.PG_NAME,
        )

    @provide(scope=Scope.APP)
    async def get_postgres_engine(self, postgres_url: URL) -> AsyncIterable[AsyncEngine]:
        async_engine = create_async_engine(
            postgres_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        logger.info("Postgres engine created")
        yield async_engine
        await async_engine.dispose()
        logger.info("Postgres engine disposed")

    @provide(scope=Scope.APP)
    async def get_postgres_session_maker(self, postgres_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            bind=postgres_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @provide(scope=Scope.REQUEST)
    async def get_postgres_session(
            self,
            postgres_session_maker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession]:
        async with postgres_session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

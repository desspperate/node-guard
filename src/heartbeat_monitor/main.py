from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka.integrations import fastapi as fastapi_integration
from fastapi import FastAPI
from loguru import logger

from heartbeat_monitor.config import HeartbeatMonitorConfig, PostgresConfig, heartbeat_monitor_config
from heartbeat_monitor.di import make_heartbeat_monitor_container
from heartbeat_monitor.error_handlers import register_error_handlers
from heartbeat_monitor.routers import ping_pong_router
from heartbeat_monitor.utils import log_settings

container = make_heartbeat_monitor_container(
    context={HeartbeatMonitorConfig: heartbeat_monitor_config},
)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up...")

    log_settings(heartbeat_monitor_config, "heartbeat monitor")

    postgres_config = await container.get(PostgresConfig)
    log_settings(postgres_config, "postgres")

    yield

    logger.info("Shutting down...")
    await container.close()

app = FastAPI(
    debug=heartbeat_monitor_config.DEBUG,
    title=heartbeat_monitor_config.FASTAPI_TITLE,
    docs_url="/docs/",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

fastapi_integration.setup_dishka(container=container, app=app)

app.include_router(ping_pong_router)

register_error_handlers(app)

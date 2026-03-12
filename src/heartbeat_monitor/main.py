from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from heartbeat_monitor.config import heartbeat_monitor_config
from heartbeat_monitor.error_handlers import register_error_handlers
from heartbeat_monitor.routers import ping_pong_router
from heartbeat_monitor.utils import log_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up...")

    log_settings(heartbeat_monitor_config, "heartbeat monitor")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    debug=heartbeat_monitor_config.DEBUG,
    title=heartbeat_monitor_config.FASTAPI_TITLE,
    docs_url="/docs/",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.include_router(ping_pong_router)

register_error_handlers(app)

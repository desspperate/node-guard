import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from node_guard.api import protected_router, router
from node_guard.config import config
from node_guard.node_controller import node_controller


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    checker_task = asyncio.create_task(node_controller.init_target_checker())
    gossip_task = asyncio.create_task(node_controller.init_gossip())

    logger.info("Background tasks started")

    yield

    logger.info("Stopping background tasks...")
    checker_task.cancel()
    gossip_task.cancel()

    await asyncio.gather(checker_task, gossip_task, return_exceptions=True)
    logger.info("Background tasks stopped")


app = FastAPI(
    debug=config.DEBUG,
    title=config.FASTAPI_TITLE,
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(protected_router)

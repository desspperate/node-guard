import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from node_guard.api import protected_router, router
from node_guard.config import config
from node_guard.node_controller import node_controller


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)

    logger.info(f"Logger configured: '{config.LOG_LEVEL}'")

    checker_task = asyncio.create_task(node_controller.init_target_checker())
    gossip_task = asyncio.create_task(node_controller.init_gossip())
    vote_resolver_task = asyncio.create_task(node_controller.init_vote_resolver())
    proactive_voter_task = asyncio.create_task(node_controller.init_proactive_voter())

    logger.info("Background tasks started")

    yield

    logger.info("Stopping background tasks...")
    checker_task.cancel()
    gossip_task.cancel()
    vote_resolver_task.cancel()
    proactive_voter_task.cancel()

    await asyncio.gather(
        checker_task,
        gossip_task,
        vote_resolver_task,
        proactive_voter_task,
        return_exceptions=True,
    )
    logger.info("Background tasks stopped")


app = FastAPI(
    debug=config.DEBUG,
    title=config.FASTAPI_TITLE,
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(protected_router)

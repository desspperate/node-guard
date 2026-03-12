from dishka import AsyncContainer, make_async_container
from pydantic_settings import BaseSettings

from .postgres_provider import PostgresProvider


def make_heartbeat_monitor_container(context: dict[type[BaseSettings], BaseSettings]) -> AsyncContainer:
    return make_async_container(
        PostgresProvider(),
        context=context,
    )


__all__ = [
    "make_heartbeat_monitor_container",
]

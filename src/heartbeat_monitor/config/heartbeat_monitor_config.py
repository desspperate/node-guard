from pydantic_settings import BaseSettings

from heartbeat_monitor.enums import EnvironmentEnum


class HeartbeatMonitorConfig(BaseSettings):
    ENV: EnvironmentEnum

    FASTAPI_TITLE: str
    DEBUG: bool


heartbeat_monitor_config = HeartbeatMonitorConfig()  # type: ignore[call-args]

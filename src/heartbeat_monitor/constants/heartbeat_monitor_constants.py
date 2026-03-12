from dataclasses import dataclass


@dataclass(frozen=True)
class HeartbeatMonitorConstants:
    WEBHOOK_URL_MAX_LENGTH = 300


heartbeat_monitor_constants = HeartbeatMonitorConstants()

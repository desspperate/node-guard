from dataclasses import dataclass


@dataclass(frozen=True)
class Constants:
    WEBHOOK_URL_MAX_LENGTH = 300
    GC_GRACE_PERIOD_SECONDS = 3600 * 24 * 7
    CHECK_TARGETS_INTERVAL_SECONDS = 10
    GOSSIP_INTERVAL_SECONDS = 2
    GOSSIP_SEED_RETRY_SECONDS = 60
    STATE_PATH = "storage/state.json"
    ID_PATH = "storage/.node_id"
    NODE_ID_PREFIX = "hbm-node-"
    NODE_ID_PREFIX_LENGTH = len(NODE_ID_PREFIX)


constants = Constants()

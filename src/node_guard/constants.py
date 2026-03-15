from dataclasses import dataclass

UUID4_HEX_LENGTH = 32


@dataclass(frozen=True)
class Constants:
    GC_GRACE_PERIOD_SECONDS = 3600 * 24 * 10
    GC_OP_COUNT_MODULO_TRIGGER = 100
    CHECK_TARGETS_INTERVAL_SECONDS = 10
    GOSSIP_INTERVAL_SECONDS = 2
    STATE_PATH = "storage/state.json"
    ID_PATH = "storage/.node_id"
    NODE_ID_PREFIX = "ng-node-"
    NODE_ID_LENGTH = len(NODE_ID_PREFIX) + UUID4_HEX_LENGTH
    CLUSTER_ID_PREFIX = "ng-cluster-"
    CLUSTER_ID_LENGTH = len(CLUSTER_ID_PREFIX) + UUID4_HEX_LENGTH


constants = Constants()

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from node_guard.constants import constants
from node_guard.crdt import CRDTSet
from node_guard.schemas import (
    CRDTSetSchema,
    ExternalStateSchema,
    InternalStateSchema,
    LastSyncSchema,
    NodesCRDTSetSchema,
    NodeValue,
)

if TYPE_CHECKING:
    from pydantic import AnyHttpUrl

class State:
    def __init__(
            self,
            nodes: CRDTSet | None = None,
            targets: CRDTSet | None = None,
            webhooks: CRDTSet | None = None,
            last_sync: LastSyncSchema | None = None,
            cluster_id: str | None = None,
    ) -> None:
        self.nodes = nodes or CRDTSet()
        self.targets = targets or CRDTSet()
        self.webhooks = webhooks or CRDTSet()
        self.last_sync: LastSyncSchema = last_sync if last_sync is not None else LastSyncSchema()
        self.cluster_id: str = cluster_id or (constants.CLUSTER_ID_PREFIX + uuid4().hex)

    def merge_state(self, external_state: ExternalStateSchema) -> None:
        peer_nodes = CRDTSet(set(external_state.nodes.added), external_state.nodes.removed)
        peer_targets = CRDTSet(set(external_state.targets.added), external_state.targets.removed)
        peer_webhooks = CRDTSet(set(external_state.webhooks.added), external_state.webhooks.removed)

        self.nodes.merge(peer_nodes)
        self.targets.merge(peer_targets)
        self.webhooks.merge(peer_webhooks)

    def is_empty(self) -> bool:
        return (
            self.targets.is_empty() and
            self.webhooks.is_empty()
        )

    def is_safe_to_exchange_with(self, node_id: str) -> bool:
        if node_id not in self.last_sync:
            return self.is_empty() or len(self.last_sync.root) > 0
        return not self._is_outdated(self.last_sync[node_id])

    def get_md5(self) -> str:
        state_str = json.dumps(self.network_format(), sort_keys=True, separators=(",", ":"))
        return hashlib.md5(state_str.encode("utf-8")).hexdigest()  # noqa: S324

    def update_last_sync(self, node_id: str) -> None:
        self.last_sync.update(node_id, datetime.now(tz=UTC))

    def save(self) -> None:
        path = Path(constants.STATE_PATH)
        path.write_text(self.get_internal_state().model_dump_json(indent=2))
        logger.debug(f"State saved to {constants.STATE_PATH}")

    def get_external_state(self) -> ExternalStateSchema:
        return ExternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            webhooks=CRDTSetSchema(added=self.webhooks.added, removed=self.webhooks.removed),
            cluster_id=self.cluster_id,
        )

    def get_internal_state(self) -> InternalStateSchema:
        return InternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            webhooks=CRDTSetSchema(added=self.webhooks.added, removed=self.webhooks.removed),
            last_sync=LastSyncSchema(self.last_sync.root),
            cluster_id=self.cluster_id,
        )

    def network_format(self) -> dict[str, dict]:
        return {
            "nodes": self.nodes.to_dict(),
            "targets": self.targets.to_dict(),
            "webhooks": self.webhooks.to_dict(),
        }

    def add_target(self, target_address: AnyHttpUrl) -> None:
        self.targets.add(str(target_address))

    def remove_target(self, target_address: AnyHttpUrl) -> None:
        self.targets.remove_item(str(target_address))

    def add_node(self, node_id: str, address: str) -> None:
        node_json = json.dumps({"node_id": node_id, "address": address}, separators=(",", ":"))
        for active in self.nodes.get_active():
            existing = NodeValue.model_validate_json(active)
            if existing.node_id == node_id:
                if active == node_json:
                    return
                self.nodes.remove_item(active)
                break
        self.nodes.add(node_json)

    @classmethod
    def from_disk(cls) -> State:
        path = Path(constants.STATE_PATH)

        if path.exists():
            validated = InternalStateSchema.model_validate_json(path.read_text())
            return cls(
                last_sync=validated.last_sync,
                nodes=CRDTSet(set(validated.nodes.added), validated.nodes.removed),
                targets=CRDTSet(set(validated.targets.added), validated.targets.removed),
                webhooks=CRDTSet(set(validated.webhooks.added), validated.webhooks.removed),
                cluster_id=validated.cluster_id,
            )

        new_state = cls()

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_state.get_internal_state().model_dump_json(indent=2))

        return new_state

    @staticmethod
    def _is_outdated(time_to_check: datetime) -> bool:
        timeout = timedelta(seconds=constants.GC_GRACE_PERIOD_SECONDS)
        return datetime.now(tz=UTC) - time_to_check > timeout

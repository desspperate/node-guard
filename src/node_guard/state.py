from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger
from pydantic import AnyHttpUrl

from node_guard.constants import constants
from node_guard.crdt import CRDTSet
from node_guard.schemas import CRDTSetSchema, ExternalStateSchema, InternalStateSchema, NodesCRDTSetSchema, NodeValue


class State:
    def __init__(
            self,
            nodes: CRDTSet | None = None,
            targets: CRDTSet | None = None,
            webhooks: CRDTSet | None = None,
            last_sync: datetime | None = None,
    ) -> None:
        self.last_sync = last_sync or datetime.now(tz=UTC)
        self.nodes = nodes or CRDTSet()
        self.targets = targets or CRDTSet()
        self.webhooks = webhooks or CRDTSet()

    def merge_state(self, external_state: ExternalStateSchema) -> None:
        peer_nodes = CRDTSet(set(external_state.nodes.added), set(external_state.nodes.removed))
        peer_targets = CRDTSet(set(external_state.targets.added), set(external_state.targets.removed))
        peer_webhooks = CRDTSet(set(external_state.webhooks.added), set(external_state.webhooks.removed))

        self.nodes.merge(peer_nodes)
        self.targets.merge(peer_targets)
        self.webhooks.merge(peer_webhooks)

    def check_last_sync(self) -> None:
        if self._is_outdated(self.last_sync):
            logger.error("State is outdated! Flashing the state to prevent zombies")
            self.nodes = CRDTSet()
            self.targets = CRDTSet()
            self.webhooks = CRDTSet()
            self.update_last_sync()

    def get_md5(self) -> str:
        state_str = json.dumps(self.network_format(), sort_keys=True, separators=(",", ":"))
        return hashlib.md5(state_str.encode("utf-8")).hexdigest()  # noqa: S324

    def update_last_sync(self) -> None:
        self.last_sync = datetime.now(tz=UTC)

    def save(self) -> None:
        with Path(constants.STATE_PATH).open("w") as f:
            json.dump(self.disk_format(), f, indent=2)
            logger.debug(f"State saved to {constants.STATE_PATH}")

    def get_external_state(self) -> ExternalStateSchema:
        return ExternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            webhooks=CRDTSetSchema(added=self.webhooks.added, removed=self.webhooks.removed),
        )

    def get_internal_state(self) -> InternalStateSchema:
        return InternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            webhooks=CRDTSetSchema(added=self.webhooks.added, removed=self.webhooks.removed),
            last_sync=self.last_sync.timestamp(),
        )

    def network_format(self) -> dict[str, dict[str, list[str]]]:
        return {
            "nodes": self.nodes.to_dict(),
            "targets": self.targets.to_dict(),
            "webhooks": self.webhooks.to_dict(),
        }

    def disk_format(self) -> dict[str, dict[str, list[str]] | float]:
        return {
            "last_sync": self.last_sync.timestamp(),
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
            raw = json.loads(path.read_text())
            validated = InternalStateSchema.model_validate(raw)
            return cls(
                last_sync=datetime.fromtimestamp(validated.last_sync, tz=UTC),
                nodes=CRDTSet(set(validated.nodes.added), set(validated.nodes.removed)),
                targets=CRDTSet(set(validated.targets.added), set(validated.targets.removed)),
                webhooks=CRDTSet(set(validated.webhooks.added), set(validated.webhooks.removed)),
            )

        new_state = cls()

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(json.dumps(new_state.disk_format(), indent=2))

        return new_state

    @staticmethod
    def _is_outdated(time_to_check: datetime) -> bool:
        timeout = timedelta(seconds=constants.GC_GRACE_PERIOD_SECONDS)
        return datetime.now(tz=UTC) - time_to_check > timeout

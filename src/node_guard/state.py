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
    SentAlertsCRDTSetSchema,
    TargetStatusVoteCRDTSetSchema,
)

if TYPE_CHECKING:
    from node_guard.enums import TargetStatus

class State:
    def __init__(  # noqa: PLR0913
            self,
            nodes: CRDTSet | None = None,
            targets: CRDTSet | None = None,
            sent_alerts: CRDTSet | None = None,
            target_status_vote: CRDTSet | None = None,
            last_sync: LastSyncSchema | None = None,
            cluster_id: str | None = None,
    ) -> None:
        self.nodes = nodes or CRDTSet()
        self.targets = targets or CRDTSet()
        self.sent_alerts = sent_alerts or CRDTSet()
        self.target_status_vote = target_status_vote or CRDTSet()
        self.last_sync: LastSyncSchema = last_sync if last_sync is not None else LastSyncSchema()
        self.cluster_id: str = cluster_id or (constants.CLUSTER_ID_PREFIX + uuid4().hex)
        self.dirty: bool = False

    def merge_state(self, external_state: ExternalStateSchema) -> None:
        peer_nodes = CRDTSet(set(external_state.nodes.added), external_state.nodes.removed)
        peer_targets = CRDTSet(set(external_state.targets.added), external_state.targets.removed)
        peer_sent_alerts = CRDTSet(set(external_state.sent_alerts.added), external_state.sent_alerts.removed)
        peer_target_status_vote = CRDTSet(
            set(external_state.target_status_vote.added),
            external_state.target_status_vote.removed,
        )

        if any([
            self.nodes.merge(peer_nodes),
            self.targets.merge(peer_targets),
            self.sent_alerts.merge(peer_sent_alerts),
            self.target_status_vote.merge(peer_target_status_vote),
        ]):
            self.dirty = True

    def is_empty(self) -> bool:
        return self.targets.is_empty()

    def is_safe_to_exchange_with(self, node_id: str) -> bool:
        if node_id not in self.last_sync:
            return self.is_empty() or len(self.last_sync.root) > 0
        return not self._is_outdated(self.last_sync[node_id])

    def get_md5(self) -> str:
        state_str = json.dumps(self.network_format(), sort_keys=True, separators=(",", ":"))
        return hashlib.md5(state_str.encode("utf-8")).hexdigest()  # noqa: S324

    def update_last_sync(self, node_id: str) -> None:
        self.last_sync.update(node_id, datetime.now(tz=UTC))
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        path = Path(constants.STATE_PATH)
        path.write_text(self.get_internal_state().model_dump_json(indent=2))
        self.dirty = False
        logger.debug(f"State saved to {constants.STATE_PATH}")

    def get_external_state(self) -> ExternalStateSchema:
        return ExternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            sent_alerts=SentAlertsCRDTSetSchema(added=self.sent_alerts.added, removed=self.sent_alerts.removed),
            target_status_vote=TargetStatusVoteCRDTSetSchema(
                added=self.target_status_vote.added,
                removed=self.target_status_vote.removed,
            ),
            cluster_id=self.cluster_id,
        )

    def get_internal_state(self) -> InternalStateSchema:
        return InternalStateSchema(
            nodes=NodesCRDTSetSchema(added=self.nodes.added, removed=self.nodes.removed),
            targets=CRDTSetSchema(added=self.targets.added, removed=self.targets.removed),
            sent_alerts=SentAlertsCRDTSetSchema(added=self.sent_alerts.added, removed=self.sent_alerts.removed),
            target_status_vote=TargetStatusVoteCRDTSetSchema(
                added=self.target_status_vote.added,
                removed=self.target_status_vote.removed,
            ),
            last_sync=LastSyncSchema(self.last_sync.root),
            cluster_id=self.cluster_id,
        )

    def network_format(self) -> dict[str, dict[str, list[str] | dict[str, float]]]:
        return {
            "nodes": self.nodes.to_dict(),
            "targets": self.targets.to_dict(),
            "sent_alerts": self.sent_alerts.to_dict(),
            "target_status_vote": self.target_status_vote.to_dict(),
        }

    def add_target(self, target_address: str) -> None:
        if self.targets.add(target_address):
            self.dirty = True

    def remove_target(self, target_address: str) -> None:
        if self.targets.remove_item(target_address):
            self.dirty = True

    def add_sent_alert(self, target: str, status: TargetStatus) -> None:
        alert_json = json.dumps({"target": target, "status": status.value}, separators=(",", ":"))
        if self.sent_alerts.add(alert_json):
            self.dirty = True

    def remove_sent_alert(self, target: str, status: TargetStatus) -> None:
        alert_json = json.dumps({"target": target, "status": status.value}, separators=(",", ":"))
        if self.sent_alerts.remove_item(alert_json):
            self.dirty = True

    def add_target_status_vote(self, target: str, node_id: str, status: TargetStatus) -> None:
        vote_json = json.dumps(
            {"target": target, "node_id": node_id, "status": status.value},
            separators=(",", ":"),
        )
        if self.target_status_vote.add(vote_json):
            self.dirty = True

    def remove_target_status_vote(self, target: str, node_id: str, status: TargetStatus) -> None:
        vote_json = json.dumps(
            {"target": target, "node_id": node_id, "status": status.value},
            separators=(",", ":"),
        )
        if self.target_status_vote.remove_item(vote_json):
            self.dirty = True

    def add_node(self, node_id: str, address: str) -> None:
        node_json = json.dumps({"node_id": node_id, "address": address}, separators=(",", ":"))
        if self.nodes.add(node_json):
            self.dirty = True

    @classmethod
    def from_disk(cls) -> State:
        path = Path(constants.STATE_PATH)

        if path.exists():
            validated = InternalStateSchema.model_validate_json(path.read_text())
            return cls(
                last_sync=validated.last_sync,
                nodes=CRDTSet(set(validated.nodes.added), validated.nodes.removed),
                targets=CRDTSet(set(validated.targets.added), validated.targets.removed),
                sent_alerts=CRDTSet(set(validated.sent_alerts.added), validated.sent_alerts.removed),
                target_status_vote=CRDTSet(
                    set(validated.target_status_vote.added),
                    validated.target_status_vote.removed,
                ),
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

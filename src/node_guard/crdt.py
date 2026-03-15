from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from node_guard.constants import constants
from node_guard.schemas import CRDTSetSchema


class CRDTSet:
    def __init__(self, added: set[str] | None = None, removed: set[str] | None = None) -> None:
        validated = CRDTSetSchema(added=added or set(), removed=removed or set())
        self.added = validated.added
        self.removed = validated.removed
        self.op_counter = 0

    def merge(self, other: CRDTSet) -> None:
        self.added |= other.added
        self.removed |= other.removed
        self.op_counter += 1
        self.try_collect_garbage()

    def get_active(self) -> set[str]:
        active_tokens = self.added - self.removed
        return {self._get_base_value(t) for t in active_tokens}

    def add(self, new_token: str) -> None:
        if not new_token or "|" in new_token:
            msg = f"Value '{new_token}' is not valid: must be non-empty and must not contain '|'"
            raise ValueError(msg)
        if new_token in self.get_active():
            return
        self.added.add(f"{new_token}|{uuid4().hex}|{datetime.now(tz=UTC).timestamp()}")
        self.op_counter += 1
        self.try_collect_garbage()

    def remove_item(self, base_value: str) -> None:
        if not base_value or "|" in base_value:
            msg = f"Value '{base_value}' is not valid: must be non-empty and must not contain '|'"
            raise ValueError(msg)
        tokens_in_added = [t for t in self.added if self._get_base_value(t) == base_value]
        for t in tokens_in_added:
            self.removed.add(t)
        self.op_counter += 1
        self.try_collect_garbage()

    def collect_garbage(self) -> None:
        to_remove_from_added: set[str] = set()
        to_remove_from_removed: set[str] = set()
        seen: dict[str, str] = {}

        for t in self.added:
            if not self._is_token_outdated(t):
                continue

            if (base_value := self._get_base_value(t)) in seen:
                token1 = t
                token2 = seen[base_value]

                if self._get_timestamp(token1) < self._get_timestamp(token2):
                    to_remove_from_added.add(token2)
                    seen[base_value] = token1
                else:
                    to_remove_from_added.add(token1)
            else:
                seen[base_value] = t

            if t in self.removed:
                to_remove_from_removed.add(t)
                to_remove_from_added.add(t)

        self.added -= to_remove_from_added
        self.removed -= to_remove_from_removed

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "added": sorted(self.added),
            "removed": sorted(self.removed),
        }

    def _is_token_outdated(self, token: str) -> bool:
        return (
            datetime.now(tz=UTC) - datetime.fromtimestamp(self._get_timestamp(token), tz=UTC)
            > timedelta(seconds=constants.GC_GRACE_PERIOD_SECONDS)
        )

    def try_collect_garbage(self) -> None:
        if self.op_counter % constants.GC_OP_COUNT_MODULO_TRIGGER == 0:
            self.collect_garbage()

    def is_empty(self) -> bool:
        return len(self.added) == 0 and len(self.removed) == 0

    @staticmethod
    def _get_base_value(token: str) -> str:
        return token.split("|", maxsplit=1)[0]

    @staticmethod
    def _get_timestamp(token: str) -> float:
        return float(token.split("|")[2])

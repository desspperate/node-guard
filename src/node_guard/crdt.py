from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from node_guard.constants import constants
from node_guard.schemas import CRDTSetSchema


class CRDTSet:
    def __init__(self, added: set[str] | None = None, removed: dict[str, float] | None = None) -> None:
        validated = CRDTSetSchema(added=added or set(), removed=removed or {})
        self.added = validated.added
        self.removed = validated.removed
        self.op_counter = 0

    def merge(self, other: CRDTSet) -> bool:
        changed = False
        new_items = other.added - self.added
        if new_items:
            self.added |= new_items
            changed = True
        for token, ts in other.removed.items():
            if token in self.removed:
                if ts < self.removed[token]:
                    self.removed[token] = ts
                    changed = True
            else:
                self.removed[token] = ts
                changed = True
        self.op_counter += 1
        self.try_collect_garbage()
        return changed

    def get_active(self) -> set[str]:
        active_tokens = self.added - self.removed.keys()
        return {self._get_base_value(t) for t in active_tokens}

    def get_active_with_created_at(self) -> dict[str, datetime]:
        active_tokens = self.added - self.removed.keys()
        return {
            self._get_base_value(t): datetime.fromtimestamp(self._get_timestamp(t), tz=UTC)
            for t in active_tokens
        }

    def add(self, new_token: str) -> bool:
        if not new_token or "|" in new_token:
            msg = f"Value '{new_token}' is not valid: must be non-empty and must not contain '|'"
            raise ValueError(msg)
        if new_token in self.get_active():
            return False
        self.added.add(f"{new_token}|{uuid4().hex}|{datetime.now(tz=UTC).timestamp()}")
        self.op_counter += 1
        self.try_collect_garbage()
        return True

    def remove_item(self, base_value: str) -> bool:
        if not base_value or "|" in base_value:
            msg = f"Value '{base_value}' is not valid: must be non-empty and must not contain '|'"
            raise ValueError(msg)
        tokens_in_added = [t for t in self.added if self._get_base_value(t) == base_value]
        if not tokens_in_added:
            return False
        now = datetime.now(tz=UTC).timestamp()
        for t in tokens_in_added:
            self.removed[t] = now
        self.op_counter += 1
        self.try_collect_garbage()
        return True

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

            if t in self.removed and self._is_timestamp_outdated(self.removed[t]):
                to_remove_from_removed.add(t)
                to_remove_from_added.add(t)

        self.added -= to_remove_from_added
        for t in to_remove_from_removed:
            del self.removed[t]

    def to_dict(self) -> dict[str, list[str] | dict[str, float]]:
        return {
            "added": sorted(self.added),
            "removed": dict(sorted(self.removed.items())),
        }

    @staticmethod
    def _is_timestamp_outdated(ts: float) -> bool:
        return (
            datetime.now(tz=UTC) - datetime.fromtimestamp(ts, tz=UTC)
            > timedelta(seconds=constants.GC_GRACE_PERIOD_SECONDS)
        )

    def _is_token_outdated(self, token: str) -> bool:
        return self._is_timestamp_outdated(self._get_timestamp(token))

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

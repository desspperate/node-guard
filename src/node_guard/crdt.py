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

    def merge(self, other: CRDTSet) -> None:
        self.added |= other.added
        self.removed |= other.removed
        self.collect_garbage()

    def get_active(self) -> set[str]:
        active_tokens = self.added - self.removed
        return {self._get_base_value(t) for t in active_tokens}

    def add(self, new_token: str) -> None:
        if not new_token or "|" in new_token:
            raise ValueError(f"Value '{new_token}' is not valid: must be non-empty and must not contain '|'")
        self.added.add(f"{new_token}|{uuid4().hex}|{datetime.now(tz=UTC).timestamp()}")
        self.collect_garbage()

    def remove_item(self, base_value: str) -> None:
        if not base_value or "|" in base_value:
            raise ValueError(f"Value '{base_value}' is not valid: must be non-empty and must not contain '|'")
        tokens_in_added = [t for t in self.added if self._get_base_value(t) == base_value]
        for t in tokens_in_added:
            self.removed.add(t)
        self.collect_garbage()

    def collect_garbage(self) -> None:
        to_remove: set[str] = set()
        for t in self.added:
            if self._is_token_outdated(t) and t in self.removed:
                to_remove.add(t)
        self.removed -= to_remove
        self.added -= to_remove

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

    @staticmethod
    def _get_base_value(token: str) -> str:
        return token.split("|", maxsplit=1)[0]

    @staticmethod
    def _get_timestamp(token: str) -> float:
        return float(token.split("|")[2])

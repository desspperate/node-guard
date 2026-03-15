from __future__ import annotations

import uuid
from pathlib import Path

from node_guard.constants import constants


class NodeID:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id

    @classmethod
    def from_disk(cls) -> NodeID:
        path = Path(constants.ID_PATH)

        if path.exists():
            content = path.read_text().strip()
            if len(content) == constants.NODE_ID_LENGTH:
                return cls(node_id=content)

        new_id = constants.NODE_ID_PREFIX + uuid.uuid4().hex

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(new_id)

        return cls(node_id=new_id)

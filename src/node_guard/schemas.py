import json
import re
from datetime import UTC, datetime

from pydantic import AnyHttpUrl, BaseModel, Field, RootModel, field_validator, model_serializer, model_validator

from node_guard.constants import constants

_TOKEN_PATTERN = re.compile(r"^[^|]+\|[0-9a-f]{32}\|\d+(\.\d+)?$")


class NodeValue(BaseModel):
    node_id: str
    address: AnyHttpUrl


class CRDTSetSchema(BaseModel):
    added: set[str] = Field(default_factory=set)
    removed: set[str] = Field(default_factory=set)

    @field_validator("added", "removed")
    @classmethod
    def validate_token_format(cls, tokens: set[str]) -> set[str]:
        for token in tokens:
            if not _TOKEN_PATTERN.match(token):
                msg = f"Invalid token format: '{token}'. Expected 'base_value|uuid4_hex|timestamp'."
                raise ValueError(msg)
        return tokens


class NodesCRDTSetSchema(CRDTSetSchema):
    @field_validator("added", "removed")
    @classmethod
    def validate_node_base_value(cls, tokens: set[str]) -> set[str]:
        for token in tokens:
            base_value = token.split("|", maxsplit=1)[0]
            try:
                NodeValue.model_validate(json.loads(base_value))
            except Exception as e:
                msg = f"Invalid node base value: '{base_value}'. Expected JSON with 'node_id' and 'address'."
                raise ValueError(msg) from e
        return tokens


class LastSyncSchema(RootModel[dict[str, datetime]]):
    root: dict[str, datetime] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _parse_timestamps(cls, data: object) -> object:
        if isinstance(data, dict):
            typed_data: dict[str, int | float | datetime] = data  # type: ignore[assignment]
            return {
                k: datetime.fromtimestamp(v, tz=UTC) if isinstance(v, (int, float)) else v
                for k, v in typed_data.items()
            }
        return data

    @model_serializer
    def _serialize_as_timestamps(self) -> dict[str, float]:
        return {k: v.timestamp() for k, v in self.root.items()}

    def get(self, node_id: str) -> datetime | None:
        return self.root.get(node_id)

    def update(self, node_id: str, dt: datetime) -> None:
        self.root[node_id] = dt

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.root

    def __getitem__(self, node_id: str) -> datetime:
        return self.root[node_id]


class StateHashSchema(BaseModel):
    hash: str


class ExternalStateSchema(BaseModel):
    nodes: NodesCRDTSetSchema
    targets: CRDTSetSchema
    webhooks: CRDTSetSchema
    cluster_id: str

    @field_validator("cluster_id")
    @classmethod
    def validate_cluster_id(cls, v: str) -> str:
        if len(v) != constants.CLUSTER_ID_LENGTH or not v.startswith(constants.CLUSTER_ID_PREFIX):
            msg = f"Invalid cluster_id: '{v}'. Expected '{constants.CLUSTER_ID_PREFIX}<uuid4_hex>'."
            raise ValueError(msg)
        return v


class InternalStateSchema(ExternalStateSchema):
    last_sync: LastSyncSchema = Field(default_factory=LastSyncSchema)


class TargetSchema(BaseModel):
    target_address: AnyHttpUrl

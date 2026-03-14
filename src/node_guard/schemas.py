import json
import re

from pydantic import BaseModel, AnyHttpUrl, Field, field_validator


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
                raise ValueError(f"Invalid token format: '{token}'. Expected 'base_value|uuid4_hex|timestamp'.")
        return tokens


class NodesCRDTSetSchema(CRDTSetSchema):
    @field_validator("added", "removed")
    @classmethod
    def validate_node_base_value(cls, tokens: set[str]) -> set[str]:
        for token in tokens:
            base_value = token.split("|", maxsplit=1)[0]
            try:
                NodeValue.model_validate(json.loads(base_value))
            except Exception:
                raise ValueError(
                    f"Invalid node base value: '{base_value}'. Expected JSON with 'node_id' and 'address'."
                )
        return tokens


class StateHashSchema(BaseModel):
    hash: str


class ExternalStateSchema(BaseModel):
    nodes: NodesCRDTSetSchema
    targets: CRDTSetSchema
    webhooks: CRDTSetSchema


class InternalStateSchema(ExternalStateSchema):
    last_sync: float


class TargetSchema(BaseModel):
    target_address: AnyHttpUrl

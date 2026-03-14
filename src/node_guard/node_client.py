from httpx import AsyncClient

from node_guard.config import config
from node_guard.schemas import ExternalStateSchema, StateHashSchema


class NodeClient:
    def __init__(self) -> None:
        self.http_client = AsyncClient()

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"X-Cluster-Token": config.CLUSTER_TOKEN.get_secret_value()}

    async def check_target(self, target_url: str) -> bool:
        response = await self.http_client.get(target_url)
        return response.status_code == 200

    async def check_state_hash(self, node_url: str, state_hash: str) -> bool:
        response = await self.http_client.post(
            node_url,
            json=StateHashSchema(hash=state_hash).model_dump(),
            headers=self._auth_headers,
        )
        return response.status_code == 200

    async def exchange_state(self, node_url: str, state: ExternalStateSchema) -> ExternalStateSchema:
        response = await self.http_client.post(
            node_url,
            json=state.model_dump(mode="json"),
            headers=self._auth_headers,
        )
        response.raise_for_status()
        return ExternalStateSchema.model_validate(response.json())


node_client: NodeClient = NodeClient()

from http import HTTPStatus

from httpx import AsyncClient, HTTPError

from node_guard.config import config
from node_guard.schemas import ExternalStateSchema, StateHashSchema


class NodeClient:
    def __init__(self) -> None:
        self.http_client = AsyncClient()

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"X-Cluster-Token": config.CLUSTER_TOKEN.get_secret_value()}

    async def check_target(self, target_url: str) -> bool:
        try:
            response = await self.http_client.get(target_url)
        except HTTPError:
            return False
        return response.status_code == HTTPStatus.OK

    async def check_state_hash(self, node_url: str, state_hash: str, caller_node_id: str, cluster_id: str) -> bool:
        response = await self.http_client.post(
            node_url,
            json=StateHashSchema(hash=state_hash).model_dump(),
            headers={**self._auth_headers, "X-Node-ID": caller_node_id, "X-Cluster-ID": cluster_id},
        )
        if response.status_code == HTTPStatus.FORBIDDEN:
            response.raise_for_status()
        return response.status_code == HTTPStatus.OK

    async def exchange_state(
            self,
            node_url: str,
            state: ExternalStateSchema,
            caller_node_id: str,
            cluster_id: str,
    ) -> ExternalStateSchema:
        response = await self.http_client.post(
            node_url,
            json=state.model_dump(mode="json"),
            headers={**self._auth_headers, "X-Node-ID": caller_node_id, "X-Cluster-ID": cluster_id},
        )
        response.raise_for_status()
        return ExternalStateSchema.model_validate(response.json())


node_client: NodeClient = NodeClient()

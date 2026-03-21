from asyncio import Semaphore
from http import HTTPStatus

from httpx import AsyncClient, HTTPError
from loguru import logger

from node_guard.config import config
from node_guard.constants import constants
from node_guard.errors import ClusterMismatchError
from node_guard.schemas import ExternalStateSchema, StateHashSchema


class NodeClient:
    def __init__(self) -> None:
        self.http_client = AsyncClient()
        self.check_target_semaphore = Semaphore(constants.MAX_CONCURRENT_TARGET_CHECKS)

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"X-Cluster-Token": config.CLUSTER_TOKEN.get_secret_value()}

    async def check_target(self, target_url: str) -> bool:
        try:
            async with self.check_target_semaphore:
                response = await self.http_client.get(target_url)
        except HTTPError as e:
            logger.trace(f"Target '{target_url}' not reachable. Reason: {e!r}. CHECK STATUS IS DOWN")
            return False
        logger.trace(f"Target '{target_url}' returned {response.status_code}")
        return response.status_code == HTTPStatus.OK

    async def check_state_hash(self, node_url: str, state_hash: str, caller_node_id: str, cluster_id: str) -> bool:
        response = await self.http_client.post(
            node_url,
            json=StateHashSchema(hash=state_hash).model_dump(),
            headers={**self._auth_headers, "X-Node-ID": caller_node_id, "X-Cluster-ID": cluster_id},
        )
        if response.status_code == HTTPStatus.FORBIDDEN:
            detail: dict[str, str] = response.json().get("detail", {})
            if isinstance(detail, dict) and "cluster_id" in detail:
                raise ClusterMismatchError(cluster_id=detail["cluster_id"])
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

    async def send_tg_message(self, user_id: int, message: str) -> None:
        token = config.TELEGRAM_BOT_TOKEN.get_secret_value()
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        payload = {
            "chat_id": user_id,
            "text": message,
        }

        response = await self.http_client.post(url, json=payload)
        response.raise_for_status()


node_client: NodeClient = NodeClient()

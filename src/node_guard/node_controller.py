import asyncio
import random
from collections.abc import Generator
from hashlib import md5

from httpx import HTTPStatusError
from loguru import logger
from pydantic import AnyHttpUrl

from node_guard.config import config
from node_guard.constants import constants
from node_guard.node_client import node_client
from node_guard.node_id import NodeID
from node_guard.schemas import ExternalStateSchema, InternalStateSchema, NodeValue, TargetSchema
from node_guard.state import State


class NodeController:
    def __init__(self, state: State | None = None, node_id: NodeID | None = None) -> None:
        self.state = state or State.from_disk()
        node_id = node_id or NodeID.from_disk()
        self.node_id = node_id.node_id
        self.state.add_node(self.node_id, config.ADVERTISED_ADDRESS)
        self.state.save()
        self.node_id_hash = int.from_bytes(md5(self.node_id.encode()).digest())  # noqa: S324

    def validate_cluster_id(self, peer_cluster_id: str) -> None:
        if len(self.state.last_sync.root) == 0:
            return
        if self.state.cluster_id != peer_cluster_id:
            msg = f"Cluster collision: own={self.state.cluster_id!r}, peer={peer_cluster_id!r}"
            raise ValueError(msg)

    def _validate_and_adopt_cluster_id(self, peer_cluster_id: str) -> None:
        if self.state.cluster_id == peer_cluster_id:
            return
        if len(self.state.last_sync.root) == 0:
            self.state.cluster_id = peer_cluster_id
            return
        msg = f"Cluster collision: own={self.state.cluster_id!r}, peer={peer_cluster_id!r}"
        raise ValueError(msg)

    def update_state(self, node_id: str, external_state: ExternalStateSchema) -> None:
        self._validate_and_adopt_cluster_id(external_state.cluster_id)
        self.state.merge_state(external_state)
        self.state.update_last_sync(node_id)
        self.state.save()

    def update_last_sync(self, node_id: str) -> None:
        self.state.update_last_sync(node_id)
        self.state.save()

    def get_internal_state(self) -> InternalStateSchema:
        return self.state.get_internal_state()

    def get_external_state(self) -> ExternalStateSchema:
        return self.state.get_external_state()

    def get_state_hash(self) -> str:
        return self.state.get_md5()

    def add_target(self, target: TargetSchema) -> None:
        self.state.add_target(target_address=target.target_address)
        self.state.save()

    def remove_target(self, target_address: AnyHttpUrl) -> None:
        self.state.remove_target(target_address=target_address)
        self.state.save()

    async def init_target_checker(self) -> None:
        while True:
            try:
                targets = self.state.targets.get_active()
                active_nodes = self.state.nodes.get_active()
                nodes_cnt = len(active_nodes)

                for t in targets:
                    ix1 = int.from_bytes(md5(t.encode()).digest()) % nodes_cnt  # noqa: S324
                    ix2 = (ix1 + 1) % nodes_cnt
                    ix3 = (ix2 + 1) % nodes_cnt

                    node_id_hash_formed = self.node_id_hash % nodes_cnt

                    if node_id_hash_formed not in {ix1, ix2, ix3}:
                        continue

                    if not await node_client.check_target(t):
                        logger.info("Target status changed... Starting Quorum!")
            except Exception as e:
                logger.exception(f"Error in target check: {e}")
            await asyncio.sleep(constants.CHECK_TARGETS_INTERVAL_SECONDS)

    def _peer_generator(self) -> Generator[tuple[str, str]]:
        # returns tuple format [node_id, node_address]
        while True:
            nodes = [NodeValue.model_validate_json(n) for n in self.state.nodes.get_active()]
            peers = [(n.node_id, str(n.address).rstrip("/")) for n in nodes if n.node_id != self.node_id]
            if not peers:
                return
            random.shuffle(peers)
            yield from peers

    async def _exchange_with(self, node_id: str, peer_address: str) -> None:
        digest_url = f"{peer_address}/internal/gossip/digest"
        cluster_id = self.state.cluster_id
        try:
            hashes_match = await node_client.check_state_hash(
                node_url=digest_url,
                state_hash=self.get_state_hash(),
                caller_node_id=self.node_id,
                cluster_id=cluster_id,
            )
        except HTTPStatusError:
            logger.critical(f"Cluster collision detected with '{node_id}:{peer_address}'. Sync BLOCKED")
            return
        if not hashes_match:
            logger.debug(f"State mismatch with {peer_address}, exchanging...")
            exchange_url = f"{peer_address}/internal/gossip/exchange"
            try:
                peer_state = await node_client.exchange_state(
                    node_url=exchange_url,
                    state=self.get_external_state(),
                    caller_node_id=self.node_id,
                    cluster_id=cluster_id,
                )
            except HTTPStatusError:
                logger.critical(f"Cluster collision detected with '{node_id}:{peer_address}'. Merge BLOCKED")
                return
            try:
                self._validate_and_adopt_cluster_id(peer_state.cluster_id)
            except ValueError:
                logger.critical(f"Cluster collision detected with '{node_id}:{peer_address}'. Merge BLOCKED")
                return
            self.state.merge_state(peer_state)
        self.state.update_last_sync(node_id)
        self.state.save()

    async def init_gossip(self) -> None:
        peer_gen = self._peer_generator()
        while True:
            try:
                peer = next(peer_gen, None)
                if peer is None:
                    peer_gen = self._peer_generator()

                    if not config.SEED_NODE:
                        logger.warning("No peers and no SEED_NODE configured, retrying in 60s...")
                        continue
                    node_id, node_address = "", config.SEED_NODE.rstrip("/")
                else:
                    node_id, node_address = peer

                logger.debug(f"Trying to exchange with '{node_id}'...")
                if not self.state.is_safe_to_exchange_with(node_id=node_id):
                    logger.critical(f"Split-brain with '{node_id}:{node_address}'. Sync BLOCKED")
                    continue

                await self._exchange_with(node_id=node_id, peer_address=node_address)
            except Exception as e:
                logger.exception(f"Error in gossip: {e}")
            finally:
                    await asyncio.sleep(constants.GOSSIP_INTERVAL_SECONDS)


node_controller: NodeController = NodeController()

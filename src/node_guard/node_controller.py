import asyncio
import random
from collections.abc import Generator
from hashlib import md5

from loguru import logger

from node_guard.config import config
from node_guard.constants import constants
from node_guard.node_id import NodeID
from node_guard.schemas import ExternalStateSchema, InternalStateSchema, NodeValue, TargetSchema
from node_guard.state import State
from node_guard.node_client import node_client


class NodeController:
    def __init__(self, state: State | None = None, node_id: NodeID | None = None) -> None:
        self.state = state or State.from_disk()
        node_id = node_id or NodeID.from_disk()
        self.node_id = node_id.node_id
        self.state.add_node(self.node_id, config.ADVERTISED_ADDRESS)
        self.state.save()
        self.node_id_hash = int.from_bytes(md5(self.node_id.encode()).digest())

    def update_state(self, external_state: ExternalStateSchema) -> None:
        self.state.merge_state(external_state)
        self.state.update_last_sync()
        self.state.save()

    def update_last_sync(self) -> None:
        self.state.update_last_sync()
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

    def remove_target(self, target: TargetSchema) -> None:
        self.state.remove_target(target_address=target.target_address)
        self.state.save()

    async def init_target_checker(self) -> None:
        while True:
            try:
                targets = self.state.targets.get_active()

                for t in targets:
                    ix1 = int.from_bytes(md5(t.encode()).digest()) % len(targets)
                    ix2 = (ix1 + 1) % len(targets)
                    ix3 = (ix2 + 1) % len(targets)

                    node_id_hash_formed = self.node_id_hash % len(targets)

                    if node_id_hash_formed in {ix1, ix2, ix3}:
                        if not await node_client.check_target(t):
                            logger.info("Target check failed... Starting Quorum!")
            except Exception as e:
                logger.exception(f"Error in target check: {e}")
            await asyncio.sleep(constants.CHECK_TARGETS_INTERVAL_SECONDS)

    def _peer_generator(self) -> Generator[str, None, None]:
        while True:
            nodes = [NodeValue.model_validate_json(n) for n in self.state.nodes.get_active()]
            peers = [str(n.address).rstrip("/") for n in nodes if n.node_id != self.node_id]
            if not peers:
                return
            random.shuffle(peers)
            yield from peers

    async def _exchange_with(self, peer_address: str) -> None:
        digest_url = f"{peer_address}/internal/gossip/digest"
        hashes_match = await node_client.check_state_hash(digest_url, self.get_state_hash())
        if not hashes_match:
            logger.debug(f"State mismatch with {peer_address}, exchanging...")
            exchange_url = f"{peer_address}/internal/gossip/exchange"
            peer_state = await node_client.exchange_state(exchange_url, self.get_external_state())
            self.state.merge_state(peer_state)
        self.state.update_last_sync()
        self.state.save()

    async def init_gossip(self) -> None:
        peer_gen = self._peer_generator()
        while True:
            try:
                peer_address = next(peer_gen, None)
                if peer_address is None:
                    peer_gen = self._peer_generator()
                    if config.SEED_NODE:
                        await self._exchange_with(config.SEED_NODE.rstrip("/"))
                    else:
                        logger.warning("No peers and no SEED_NODE configured, retrying in 60s...")
                        await asyncio.sleep(constants.GOSSIP_SEED_RETRY_SECONDS)
                        continue
                else:
                    await self._exchange_with(peer_address)
            except Exception as e:
                logger.exception(f"Error in gossip: {e}")
                await asyncio.sleep(constants.GOSSIP_SEED_RETRY_SECONDS)
                continue
            await asyncio.sleep(constants.GOSSIP_INTERVAL_SECONDS)


node_controller: NodeController = NodeController()

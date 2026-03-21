import asyncio
import itertools
import random
import time
from collections import defaultdict, deque
from collections.abc import Coroutine, Generator
from datetime import UTC, datetime, timedelta
from hashlib import md5
from typing import Any

from httpx import HTTPStatusError
from loguru import logger

from node_guard.config import config
from node_guard.constants import constants
from node_guard.enums import TargetStatus
from node_guard.errors import ClusterMismatchError
from node_guard.node_client import node_client
from node_guard.node_id import NodeID
from node_guard.schemas import (
    ExternalStateSchema,
    InternalStateSchema,
    NodeValue,
    SentAlertValue,
    TargetSchema,
    TargetsSchema,
    TargetStatusVoteValue,
)
from node_guard.state import State


class NodeController:
    def __init__(self, state: State | None = None, node_id: NodeID | None = None) -> None:
        self.state = state or State.from_disk()
        node_id = node_id or NodeID.from_disk()
        self.node_id = node_id.node_id
        self.state.add_node(self.node_id, config.ADVERTISED_ADDRESS)
        self.state.save()
        self.target_check_log: defaultdict[str, deque[TargetStatus]] = defaultdict(
            lambda: deque(maxlen=max(constants.DOWN_WINDOW_SIZE, constants.UP_WINDOW_SIZE)),
        )
        self.start_time = time.monotonic()
        self._background_tasks: set[asyncio.Task[Any]] = set()

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
            logger.info(f"Adopting peer cluster_id: {peer_cluster_id!r} (was {self.state.cluster_id!r})")
            self.state.cluster_id = peer_cluster_id
            self.state.dirty = True
            return
        msg = f"Cluster collision: own={self.state.cluster_id!r}, peer={peer_cluster_id!r}"
        raise ValueError(msg)

    def update_last_sync(self, node_id: str) -> None:
        self.state.update_last_sync(node_id)
        self.state.save()

    def get_internal_state(self) -> InternalStateSchema:
        return self.state.get_internal_state()

    def get_external_state(self) -> ExternalStateSchema:
        return self.state.get_external_state()

    def get_state_hash(self) -> str:
        return self.state.get_md5()

    def get_targets(self) -> TargetsSchema:
        return TargetsSchema(targets=sorted(self.state.targets.get_active()))

    def add_target(self, target: TargetSchema) -> None:
        self.state.add_target(target_address=target.target_address)
        self.state.save()
        logger.info(f"Target added: '{target.target_address}'")

    def remove_target(self, target_address: str) -> None:
        self.state.remove_target(target_address=target_address)
        self.state.save()
        logger.info(f"Target removed: '{target_address}'")

    async def _run_target_check_cycle(self) -> None:
        active_nodes = sorted(self.state.nodes.get_active())
        node_ix = self._get_node_ix(self.node_id, active_nodes)
        nodes_cnt = len(active_nodes)

        all_targets = self.state.targets.get_active()
        assigned_targets = [
            t for t in all_targets
            if self._is_node_responsible_for_target(t, node_ix, nodes_cnt)
        ]
        logger.debug(
            f"Target check cycle: {len(all_targets)} total targets, "
            f"{len(assigned_targets)} assigned to this node (ix={node_ix}/{nodes_cnt})",
        )
        if not assigned_targets:
            return

        sent_alerts = self.state.sent_alerts.get_active_with_created_at()
        last_alerts_map = self._get_last_alerts_map(sent_alerts)

        tasks = [
            self._process_target_check(
                target=target,
                previous_status=last_alerts_map.get(target),
            )
            for target in assigned_targets
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_target_check(
            self,
            target: str,
            previous_status: TargetStatus | None,
    ) -> None:
        try:
            is_up = await node_client.check_target(target)
            target_status = TargetStatus.UP if is_up else TargetStatus.DOWN
            logger.debug(f"Target '{target}' check status is '{target_status.value}'")
            logger.trace(f"Target '{target} previous status is '{previous_status}'")
            self.target_check_log[target].appendleft(target_status)
            updated_status = self._evaluate_status_change(
                target=target,
                previous_status=previous_status,
                log_window=self.target_check_log[target],
            )
            if updated_status:
                logger.info(f"Adding a vote that target '{target}' is '{updated_status}' now")
                self.state.add_target_status_vote(
                    target=target,
                    node_id=self.node_id,
                    status=updated_status,
                )
                self.state.remove_target_status_vote(
                    target=target,
                    node_id=self.node_id,
                    status=TargetStatus.DOWN if updated_status is TargetStatus.UP else TargetStatus.UP,
                )
                self.state.save()
        except Exception as e:
            logger.exception(f"Unhandled error while processing target '{target}': {e}")

    @staticmethod
    def _evaluate_status_change(
            target: str,
            previous_status: TargetStatus | None,
            log_window: deque[TargetStatus],
    ) -> TargetStatus | None:
        if len(log_window) < min(constants.UP_WINDOW_SIZE, constants.DOWN_WINDOW_SIZE):
            logger.info(f"Target {target} log window is not filled up enough to make a decision")
            return None
        if previous_status in (TargetStatus.DOWN, None):
            up_logs_cnt = log_window.count(TargetStatus.UP)
            window_len = len(log_window)
            success_rate = up_logs_cnt / window_len
            logger.trace(
                f"Target {target} | Eval UP | Prev: {previous_status} | "
                f"UPs: {up_logs_cnt}/{window_len} | "
                f"Success Rate: {success_rate:.1%} (Threshold: {constants.UP_SUCCESS_RATE_THRESHOLD:.1%}) | "
                f"Window: {[s.value for s in log_window]}",
            )
            if success_rate >= constants.UP_SUCCESS_RATE_THRESHOLD:
                return TargetStatus.UP
        if previous_status in (TargetStatus.UP, None):
            cutted_log_window = list(itertools.islice(log_window, constants.DOWN_WINDOW_SIZE))
            down_logs_cnt = cutted_log_window.count(TargetStatus.DOWN)
            window_len = len(cutted_log_window)
            failure_rate = down_logs_cnt / window_len
            logger.trace(
                f"Target {target} | Eval DOWN | Prev: {previous_status} | "
                f"DOWNs: {down_logs_cnt}/{window_len} | "
                f"Failure Rate: {failure_rate:.1%} (Threshold: {constants.DOWN_FAILURE_RATE_THRESHOLD:.1%}) | "
                f"Window: {[s.value for s in cutted_log_window]}",
            )
            if failure_rate >= constants.DOWN_FAILURE_RATE_THRESHOLD:
                return TargetStatus.DOWN
        return None

    @staticmethod
    def _get_last_alerts_map(raw_alerts_with_ts: dict[str, datetime]) -> dict[str, TargetStatus]:
        last_alerts_map: dict[str, TargetStatus] = {}
        last_timestamps: dict[str, datetime] = {}

        for raw_alert_json, dt in raw_alerts_with_ts.items():
            try:
                alert = SentAlertValue.model_validate_json(raw_alert_json)
                target_key = alert.target

                if target_key not in last_timestamps or dt > last_timestamps[target_key]:
                    last_alerts_map[target_key] = alert.status
                    last_timestamps[target_key] = dt

            except Exception as e:
                logger.error(f"Failed to parse alert JSON during map building: {e}")
                continue

        return last_alerts_map

    @staticmethod
    def _is_node_responsible_for_target(target: str, node_ix: int, nodes_cnt: int) -> int:
        ix1 = int.from_bytes(md5(target.encode()).digest()) % nodes_cnt  # noqa: S324
        ix2 = (ix1 + 1) % nodes_cnt
        ix3 = (ix2 + 1) % nodes_cnt
        if node_ix == ix1:
            return 1
        if node_ix == ix2:
            return 2
        if node_ix == ix3:
            return 3
        return 0

    @staticmethod
    def _get_node_ix(node_id: str, active_nodes: list[str]) -> int:
        for ix, n in enumerate(active_nodes):
            if node_id in n:
                return ix
        msg = f"Node {node_id} not found in a cluster active nodes list"
        raise ValueError(msg)

    async def init_target_checker(self) -> None:
        while True:
            try:
                await self._run_target_check_cycle()
            except Exception as e:
                logger.exception(f"Error in target check: {e}")
            finally:
                await asyncio.sleep(constants.CHECK_TARGETS_INTERVAL_SECONDS)

    @staticmethod
    def _quorum_decision(nodes_cnt: int, up_votes: int, down_votes: int) -> TargetStatus | None:
        quorum_needed = (nodes_cnt + 1) // 2
        if up_votes >= quorum_needed:
            return TargetStatus.UP
        if down_votes >= quorum_needed:
            return TargetStatus.DOWN
        return None

    @staticmethod
    def _get_responsible_peers(
            raw_nodes: list[str],
            node_id: str,
            target: str,
    ) -> list[tuple[str, str]]:
        if not raw_nodes:
            return []

        active_nodes_str = sorted(raw_nodes)
        nodes_cnt = len(active_nodes_str)

        ix1 = int.from_bytes(md5(target.encode()).digest()) % nodes_cnt  # noqa: S324
        ix2 = (ix1 + 1) % nodes_cnt
        ix3 = (ix2 + 1) % nodes_cnt

        responsible_indices = {ix1, ix2, ix3}
        peers: list[tuple[str, str]] = []

        for ix in responsible_indices:
            node_val = NodeValue.model_validate_json(active_nodes_str[ix])
            if node_val.node_id != node_id:
                peers.append((node_val.node_id, node_val.address))

        return peers

    async def _process_target_vote(
            self,
            target: str,
            node_ix: int,
            active_nodes: list[str],
            votes: list[tuple[TargetStatusVoteValue, datetime]],
    ) -> None:
        try:
            nodes_cnt = len(active_nodes)
            up_votes_cnt = sum(1 for v, _ in votes if v.status == TargetStatus.UP)
            down_votes_cnt = len(votes) - up_votes_cnt
            logger.trace(
                f"Vote processing for '{target}': UP={up_votes_cnt}, DOWN={down_votes_cnt}, "
                f"total={len(votes)}, quorum_needed={nodes_cnt // 2 + 1}",
            )

            if (quorum_decision := self._quorum_decision(
                nodes_cnt=nodes_cnt,
                up_votes=up_votes_cnt,
                down_votes=down_votes_cnt,
            )) is None:
                logger.debug(f"No quorum reached for '{target}', skipping")
                return
            last_vote_dt = max((dt for _, dt in votes), default=None)
            if last_vote_dt is None:
                logger.debug(f"Somehow can't find last vote for '{target}'. Skipping...")
                return
            responsibility_level = self._is_node_responsible_for_target(
                target=target,
                node_ix=node_ix,
                nodes_cnt=nodes_cnt,
            )
            if responsibility_level == 0:
                logger.debug(f"Not responsible for sending alert for '{target}', skipping")
                return
            responsible_ix = responsibility_level - 1

            now = datetime.now(tz=UTC)
            delay = timedelta(seconds=responsible_ix * constants.SEND_ALERT_ONE_IX_DELAY)
            if now < last_vote_dt + delay:
                logger.debug(
                    f"Waiting stagger delay (ix={responsible_ix}) for '{target}', "
                    f"eligible at {(last_vote_dt + delay).strftime('%H:%M:%S')}",
                )
                return

            template = (
                constants.TARGET_UP_ALERT_MESSAGE if quorum_decision is TargetStatus.UP
                else constants.TARGET_DOWN_ALERT_MESSAGE
            )
            message = template.format(target, last_vote_dt.strftime("%Y-%m-%d %H:%M:%S %Z"), self.node_id)

            logger.info(f"Sending {quorum_decision.value} alert for '{target}' (last_vote_dt={last_vote_dt})")
            await node_client.send_tg_message(
                message=message,
                user_id=config.TELEGRAM_CHAT_ID,
            )
            logger.info(f"Alert sent for '{target}': {quorum_decision.value}")

            for vote, _ in votes:
                self.state.remove_target_status_vote(target=vote.target, node_id=vote.node_id, status=vote.status)
            reversed_decision = TargetStatus.DOWN if quorum_decision is TargetStatus.UP else TargetStatus.UP
            self.state.remove_sent_alert(
                target=target,
                status=reversed_decision,
            )
            self.state.add_sent_alert(
                target=target,
                status=quorum_decision,
            )

            self.state.save()

            peers_to_notify = self._get_responsible_peers(
                raw_nodes=active_nodes,
                node_id=self.node_id,
                target=target,
            )
            for peer_id, peer_addr in peers_to_notify:
                logger.info(f"Extraordinary gossip to {peer_id} about alert on {target}")
                self._run_background_task(self._exchange_with(node_id=peer_id, peer_address=peer_addr))
        except Exception as e:
            logger.exception(f"Error in target vote resolving: '{e}'")

    async def init_vote_resolver(self) -> None:
        while True:
            try:
                elapsed = time.monotonic() - self.start_time
                if elapsed <= constants.GOSSIP_WARMUP_TIME:
                    logger.debug(f"Vote resolver in warmup, {constants.GOSSIP_WARMUP_TIME - elapsed:.0f}s remaining")
                    continue

                grouped_votes: defaultdict[str, list[tuple[TargetStatusVoteValue, datetime]]] = defaultdict(list)

                raw_votes = self.state.target_status_vote.get_active_with_created_at()
                for raw_vote, dt in raw_votes.items():
                    vote = TargetStatusVoteValue.model_validate_json(raw_vote)
                    grouped_votes[vote.target].append((vote, dt))
                logger.debug(f"Vote resolver: {len(raw_votes)} votes across {len(grouped_votes)} targets")

                active_nodes = sorted(self.state.nodes.get_active())
                node_ix = self._get_node_ix(self.node_id, active_nodes)
                for target, votes in grouped_votes.items():
                    await self._process_target_vote(
                        target=target,
                        node_ix=node_ix,
                        active_nodes=active_nodes,
                        votes=votes,
                    )
            except Exception as e:
                logger.exception(f"Error in vote resolving: {e}")
            finally:
                await asyncio.sleep(constants.VOTE_RESOLVE_INTERVAL_SECONDS)

    async def _process_proactive_target_vote(
            self,
            target: str,
            node_ix: int,
            nodes_cnt: int,
            *,
            did_vote: bool,
    ) -> None:
        if did_vote:
            return

        if self._is_node_responsible_for_target(
                target=target,
                node_ix=node_ix,
                nodes_cnt=nodes_cnt,
        ):
            return

        try:
            is_up = await node_client.check_target(target)
        except Exception as e:
            logger.exception(f"Error during checking target: {e}")
            return
        target_status = TargetStatus.UP if is_up else TargetStatus.DOWN
        logger.info(f"Proactive vote: '{target}' is {target_status.value}")
        self.state.add_target_status_vote(
            target=target,
            node_id=self.node_id,
            status=target_status,
        )
        self.state.save()

    async def init_proactive_voter(self) -> None:
        while True:
            try:
                raw_votes = self.state.target_status_vote.get_active()

                targets_with_votes: set[str] = set()
                my_votes: set[str] = set()

                for raw_vote in raw_votes:
                    vote = TargetStatusVoteValue.model_validate_json(raw_vote)
                    targets_with_votes.add(vote.target)
                    if vote.node_id == self.node_id:
                        my_votes.add(vote.target)

                active_nodes = sorted(self.state.nodes.get_active())
                node_ix = self._get_node_ix(self.node_id, active_nodes)
                logger.debug(
                    f"Proactive voter: {len(targets_with_votes)} targets with votes, "
                    f"{len(my_votes)} already voted by this node",
                )

                tasks = [
                    self._process_proactive_target_vote(
                        target=target,
                        did_vote=(target in my_votes),
                        node_ix=node_ix,
                        nodes_cnt=len(active_nodes),
                    )
                    for target in targets_with_votes
                ]

                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.exception(f"Error in proactive voting: {e}")
            finally:
                await asyncio.sleep(constants.PROACTIVE_VOTER_INTERVAL_SECONDS)

    def _peer_generator(self) -> Generator[tuple[str, str]]:
        """

        :return: tuple [node_id, node_address]
        """
        while True:
            nodes = [NodeValue.model_validate_json(n) for n in self.state.nodes.get_active()]
            peers = [(n.node_id, n.address) for n in nodes if n.node_id != self.node_id]
            if not peers:
                return
            random.shuffle(peers)
            yield from peers

    async def _exchange_with(self, node_id: str, peer_address: str) -> None:
        digest_url = f"{peer_address}/internal/gossip/digest"
        try:
            hashes_match = await node_client.check_state_hash(
                node_url=digest_url,
                state_hash=self.get_state_hash(),
                caller_node_id=self.node_id,
                cluster_id=self.state.cluster_id,
            )
        except ClusterMismatchError as e:
            if len(self.state.last_sync.root) > 0:
                logger.critical(f"Cluster collision detected with '{node_id}:{peer_address}'. Sync BLOCKED")
                return
            self._validate_and_adopt_cluster_id(e.cluster_id)
            self.state.save()
            try:
                hashes_match = await node_client.check_state_hash(
                    node_url=digest_url,
                    state_hash=self.get_state_hash(),
                    caller_node_id=self.node_id,
                    cluster_id=self.state.cluster_id,
                )
            except HTTPStatusError:
                logger.critical(f"Cluster collision on retry with '{node_id}:{peer_address}'. Sync BLOCKED")
                return
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
                    cluster_id=self.state.cluster_id,
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

    def _run_background_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)


node_controller: NodeController = NodeController()

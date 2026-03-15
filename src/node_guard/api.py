from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger
from pydantic import AnyHttpUrl

from node_guard.config import config
from node_guard.node_controller import node_controller
from node_guard.schemas import ExternalStateSchema, InternalStateSchema, StateHashSchema, TargetSchema


def verify_token(x_cluster_token: str = Header()) -> None:
    if x_cluster_token != config.CLUSTER_TOKEN.get_secret_value():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid cluster token")


router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(verify_token)])


@router.get("/ping")
def ping_pong() -> str:
    return "pong"


@protected_router.get("/api/state", response_model=InternalStateSchema)
def get_state() -> InternalStateSchema:
    return node_controller.get_internal_state()


@protected_router.post("/api/target", response_model=InternalStateSchema)
def create_target(target: TargetSchema) -> InternalStateSchema:
    node_controller.add_target(target=target)
    return node_controller.get_internal_state()


@protected_router.delete("/api/state/{target_address}", response_model=InternalStateSchema)
def delete_target(target_address: AnyHttpUrl) -> InternalStateSchema:
    node_controller.remove_target(target_address=target_address)
    return node_controller.get_internal_state()


@protected_router.post("/internal/gossip/digest", status_code=status.HTTP_200_OK)
def gossip_digest(state_hash: StateHashSchema, x_node_id: str = Header(), x_cluster_id: str = Header()) -> None:
    logger.debug(f"Gossip digest with '{x_node_id}'")
    try:
        node_controller.validate_cluster_id(x_cluster_id)
    except ValueError as e:
        logger.critical(f"Cluster collision detected from '{x_node_id}'. BLOCKED")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    if node_controller.get_state_hash() != state_hash.hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    node_controller.update_last_sync(node_id=x_node_id)


@protected_router.post("/internal/gossip/exchange", response_model=ExternalStateSchema)
def gossip_exchange(state: ExternalStateSchema, x_node_id: str = Header()) -> ExternalStateSchema:
    logger.debug(f"Gossip exchange with '{x_node_id}'")
    try:
        node_controller.update_state(node_id=x_node_id, external_state=state)
    except ValueError as e:
        logger.critical(f"Cluster collision detected from '{x_node_id}'. Merge BLOCKED")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return node_controller.get_external_state()

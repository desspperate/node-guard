from fastapi import APIRouter, Depends, Header, HTTPException, status

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


@protected_router.delete("/api/state", response_model=InternalStateSchema)
def delete_target(target: TargetSchema) -> InternalStateSchema:
    node_controller.remove_target(target=target)
    return node_controller.get_internal_state()


@protected_router.post("/internal/gossip/digest", status_code=status.HTTP_200_OK)
def gossip_digest(state_hash: StateHashSchema) -> None:
    if node_controller.get_state_hash() != state_hash.hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    else:
        node_controller.update_last_sync()


@protected_router.post("/internal/gossip/exchange", response_model=ExternalStateSchema)
def gossip_exchange(state: ExternalStateSchema) -> ExternalStateSchema:
    node_controller.update_state(external_state=state)
    return node_controller.get_external_state()

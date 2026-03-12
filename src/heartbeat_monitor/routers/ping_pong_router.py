from fastapi import APIRouter

router = APIRouter(
    tags=["PingPong"],
)


@router.get("/ping")
async def ping_pong() -> str:
    return "pong"

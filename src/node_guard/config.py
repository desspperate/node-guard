from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    FASTAPI_TITLE: str
    DEBUG: bool
    ADVERTISED_ADDRESS: str
    CLUSTER_TOKEN: SecretStr
    SEED_NODE: str
    LOG_LEVEL: str
    TELEGRAM_BOT_TOKEN: SecretStr
    TELEGRAM_CHAT_ID: int


config = Config()  # type: ignore[call-args]

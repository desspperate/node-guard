from loguru import logger
from pydantic_settings import BaseSettings


def log_settings(settings: BaseSettings, title: str) -> None:
    logger.info(f"⚙️ {title} ⚙️")

    fields = type(settings).model_fields
    max_key_length = max(len(key) for key in fields) + 2

    for key in sorted(fields.keys()):
        value = getattr(settings, key)
        value_str = str(value)
        logger.info(f"{key:<{max_key_length}}: {value_str}")

    logger.info("─" * (max_key_length + 20))

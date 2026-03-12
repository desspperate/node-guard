from pydantic import SecretStr
from pydantic_settings import BaseSettings


class PostgresConfig(BaseSettings):
    PG_USER: str
    PG_PASSWORD: SecretStr
    PG_NAME: str
    PG_DRIVER: str
    PG_HOST: str
    PG_PORT: int

    @property
    def dsn(self) -> str:
        return (f"postgresql://{self.PG_USER}:{self.PG_PASSWORD.get_secret_value()}@{self.PG_HOST}:"
                f"{self.PG_PORT}/{self.PG_NAME}")

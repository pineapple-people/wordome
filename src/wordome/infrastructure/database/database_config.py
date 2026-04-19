from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    account: str
    user: str
    password: str
    warehouse: str = "COMPUTE_WH"
    database: str
    schema: str = "PUBLIC"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SNOWFLAKE_")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

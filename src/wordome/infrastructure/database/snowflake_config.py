from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SnowflakeConfig(BaseSettings):
    account: str
    user: str
    password: str
    warehouse: str
    database: str
    schema: str

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SNOWFLAKE_")


@lru_cache(maxsize=1)
def get_snowflake_config() -> SnowflakeConfig:
    return SnowflakeConfig()

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SnowflakeProfile(BaseSettings):
    account: str
    user: str
    password: str
    warehouse: str
    database: str
    schema_name: str

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SNOWFLAKE_")


@lru_cache(maxsize=1)
def get_snowflake_profile() -> SnowflakeProfile:
    return SnowflakeProfile()

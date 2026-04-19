from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    account: str
    user: str
    password: str
    warehouse: str = "COMPUTE_WH"
    database: str
    schema: str = "PUBLIC"

    class Config:
        env_file = ".env"
        # Map environment variables to fields
        env_prefix = "SNOWFLAKE_"


settings = Settings()

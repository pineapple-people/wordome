import asyncio

from sqlalchemy import text

from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeEntryRecord,
    ReviewScrapeRecord,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_config
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


async def bootstrap_snowflake() -> dict[str, object]:
    config = get_snowflake_config()
    connection = SnowflakeConnection()

    quoted_database = _quote_identifier(config.database)
    quoted_schema = _quote_identifier(config.schema)

    await connection.run_session(
        lambda session: session.execute(
            text(f"CREATE DATABASE IF NOT EXISTS {quoted_database}")
        )
    )
    await connection.run_session(
        lambda session: session.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {quoted_database}.{quoted_schema}")
        )
    )
    await connection.create_all()

    return {
        "success": True,
        "database": config.database,
        "schema": config.schema,
        "review_scrapes_table": ReviewScrapeRecord.__tablename__,
        "review_scrape_records_table": ReviewScrapeEntryRecord.__tablename__,
    }


def main() -> None:
    result = asyncio.run(bootstrap_snowflake())
    print(result)


if __name__ == "__main__":
    main()

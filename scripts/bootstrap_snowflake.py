import asyncio

from sqlalchemy import text

from wordome.infrastructure.database.review_scrape_orm import ReviewScrapeRecord
from wordome.infrastructure.database.snowflake_config import get_snowflake_config
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _is_safe_rename_noop(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "does not exist" in message
        or "invalid identifier" in message
        or "already exists" in message
    )


async def bootstrap_snowflake() -> dict[str, object]:
    config = get_snowflake_config()
    connection = SnowflakeConnection()

    quoted_database = _quote_identifier(config.database)
    quoted_schema = _quote_identifier(config.schema)
    table_name = (
        f"{quoted_database}.{quoted_schema}.{ReviewScrapeRecord.__tablename__}"
    )

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

    try:
        await connection.run_session(
            lambda session: session.execute(
                text(
                    f"""
                    ALTER TABLE {table_name}
                    RENAME COLUMN snapshot_id TO snapshot_event_id
                    """
                )
            )
        )
    except Exception as exc:
        if not _is_safe_rename_noop(exc):
            raise RuntimeError(
                "Failed to rename legacy column 'snapshot_id' to "
                f"'snapshot_event_id' on {table_name}. Original error: {exc}"
            ) from exc

    await connection.run_session(
        lambda session: session.execute(
            text(
                f"""
                ALTER TABLE {table_name}
                ADD COLUMN IF NOT EXISTS snapshot_hash STRING
                """
            )
        )
    )

    return {
        "success": True,
        "database": config.database,
        "schema": config.schema,
        "review_scrapes_table": ReviewScrapeRecord.__tablename__,
    }


def main() -> None:
    result = asyncio.run(bootstrap_snowflake())
    print(result)


if __name__ == "__main__":
    main()

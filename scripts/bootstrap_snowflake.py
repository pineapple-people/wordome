import asyncio
import json

from sqlalchemy import text

from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeEntryRecord,
    ReviewScrapeQueueRecord,
    ReviewScrapeRecord,
    ReviewScrapeRunRecord,
)
from wordome.infrastructure.database.sitemap_crawl_orm import (
    SitemapCrawlRecord,
    SitemapCrawlRunRecord,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_profile
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


async def bootstrap_snowflake() -> dict[str, object]:
    config = get_snowflake_profile()
    connection = SnowflakeConnection()

    quoted_database = _quote_identifier(config.database)
    quoted_schema = _quote_identifier(config.schema_name)

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
        "schema": config.schema_name,
        "review_scrapes_table": ReviewScrapeRecord.__tablename__,
        "review_scrape_queue_table": ReviewScrapeQueueRecord.__tablename__,
        "review_scrape_pipeline_runs_table": ReviewScrapeRunRecord.__tablename__,
        "sitemap_crawl_runs_table": SitemapCrawlRunRecord.__tablename__,
        "sitemap_crawl_records_table": SitemapCrawlRecord.__tablename__,
        "review_scrape_records_table": ReviewScrapeEntryRecord.__tablename__,
    }


def main() -> None:
    result = asyncio.run(bootstrap_snowflake())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

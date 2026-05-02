from sqlalchemy import create_engine

from wordome.app import create_app
from wordome.infrastructure.database.review_scrape_orm import (
    Base,
    ReviewScrapeEntryRecord,
    ReviewScrapeQueueRecord,
    ReviewScrapeRecord,
    ReviewScrapeRunRecord,
)
from wordome.infrastructure.database.sitemap_crawl_orm import (
    SitemapCrawlRecord,
    SitemapCrawlRunRecord,
)
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


def main() -> None:
    expected_tables = {
        ReviewScrapeRecord.__tablename__,
        ReviewScrapeEntryRecord.__tablename__,
        ReviewScrapeQueueRecord.__tablename__,
        ReviewScrapeRunRecord.__tablename__,
        SitemapCrawlRunRecord.__tablename__,
        SitemapCrawlRecord.__tablename__,
    }
    registered_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - {
        table_name.split(".")[-1] for table_name in registered_tables
    }
    if missing_tables:
        raise RuntimeError(f"Missing ORM table registrations: {sorted(missing_tables)}")

    app = create_app()
    if not hasattr(app.state, "ikea_scraper"):
        raise RuntimeError("App is missing `ikea_scraper` state")
    if not hasattr(app.state, "sitemap_pdp_discoverer"):
        raise RuntimeError("App is missing `sitemap_pdp_discoverer` state")

    connection = SnowflakeConnection(engine=create_engine("sqlite:///:memory:"))
    if connection is None:
        raise RuntimeError("Failed to instantiate SnowflakeConnection")

    print("smoke_checks=ok")
    print(f"registered_tables={sorted(expected_tables)}")
    print("app_state=ok")
    print("snowflake_connection_import=ok")


if __name__ == "__main__":
    main()

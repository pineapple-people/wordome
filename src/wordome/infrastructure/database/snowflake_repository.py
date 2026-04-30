from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select

from wordome.domain.reviews.models import ReviewScrapeResult
from wordome.domain.sitemaps import (
    SitemapCrawlRecordObservation,
    SitemapPdpDiscoveryResult,
)
from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeEntryRecord,
    ReviewScrapeRecord,
)
from wordome.infrastructure.database.review_scrape_result_codec import (
    ReviewScrapeResultCodec,
)
from wordome.infrastructure.database.sitemap_crawl_orm import (
    SitemapCrawlRecord,
    SitemapCrawlRunRecord,
    SitemapCrawlRunStatus,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_profile
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


class SnowflakeRepository:
    """
    Business logic for Snowflake persistence via SQLAlchemy ORM.
    """

    REVIEW_SCRAPES_TABLE = ReviewScrapeRecord.__tablename__
    SITEMAP_CRAWL_RUNS_TABLE = SitemapCrawlRunRecord.__tablename__
    SITEMAP_CRAWL_RECORDS_TABLE = SitemapCrawlRecord.__tablename__
    REVIEW_SCRAPE_RECORDS_TABLE = ReviewScrapeEntryRecord.__tablename__
    NEW_YORK_TZ = ZoneInfo("America/New_York")

    def __init__(self, connection: SnowflakeConnection | None = None):
        self._connection = connection or SnowflakeConnection()
        self._config = get_snowflake_profile() if connection is None else None

    async def is_connected(self) -> bool:
        return await self._connection.is_connected()

    async def get_repository_health(self) -> dict[str, Any]:
        is_connected = await self.is_connected()
        result: dict[str, Any] = {
            "database_connected": is_connected,
            "service": "wordome",
            "timestamp": datetime.now(UTC).isoformat(),
            "configured_database": self._config.database if self._config else None,
            "configured_schema": self._config.schema_name if self._config else None,
            "review_scrapes_table": self.REVIEW_SCRAPES_TABLE,
            "sitemap_crawl_runs_table": self.SITEMAP_CRAWL_RUNS_TABLE,
            "sitemap_crawl_records_table": self.SITEMAP_CRAWL_RECORDS_TABLE,
            "review_scrape_records_table": self.REVIEW_SCRAPE_RECORDS_TABLE,
            "current_context": None,
            "database_visible": None,
            "schema_visible": None,
            "review_scrapes_table_exists": None,
            "review_scrape_records_table_exists": None,
            "can_bootstrap_schema": None,
            "accessible_databases": [],
            "accessible_schemas_in_configured_database": [],
            "accessible_tables_in_configured_schema": [],
            "grants_to_current_role": [],
            "errors": [],
        }

        if not is_connected:
            return result

        try:
            result["current_context"] = await self._connection.get_current_context()
        except Exception as exc:
            result["errors"].append(f"Unable to fetch current Snowflake context: {exc}")

        if self._config is None:
            history_table_exists = await self._safe_table_exists(
                ReviewScrapeRecord.__tablename__
            )
            state_table_exists = await self._safe_table_exists(
                ReviewScrapeEntryRecord.__tablename__
            )
            result["review_scrapes_table_exists"] = history_table_exists
            result["review_scrape_records_table_exists"] = state_table_exists
            result["can_bootstrap_schema"] = history_table_exists and state_table_exists
            result["grants_to_current_role"] = await self._safe_grants_to_current_role()
            return result

        accessible_databases = await self._list_accessible_databases()
        result["accessible_databases"] = accessible_databases
        result["database_visible"] = self._config.database in accessible_databases

        if result["database_visible"]:
            accessible_schemas = await self._list_accessible_schemas(
                self._config.database
            )
            result["accessible_schemas_in_configured_database"] = accessible_schemas
            result["schema_visible"] = self._config.schema_name in accessible_schemas
        else:
            result["errors"].append(
                f"Configured database '{self._config.database}' is not visible."
            )

        if result["database_visible"] and result["schema_visible"]:
            result[
                "accessible_tables_in_configured_schema"
            ] = await self._list_accessible_tables(
                self._config.database,
                self._config.schema_name,
            )
            result["review_scrapes_table_exists"] = await self._safe_table_exists(
                ReviewScrapeRecord.__tablename__
            )
            result[
                "review_scrape_records_table_exists"
            ] = await self._safe_table_exists(ReviewScrapeEntryRecord.__tablename__)
            result["can_bootstrap_schema"] = True
        elif result["database_visible"]:
            result["errors"].append(
                f"Configured schema '{self._config.schema_name}' is not visible in database "
                f"'{self._config.database}'."
            )

        result["grants_to_current_role"] = await self._safe_grants_to_current_role()
        return result

    async def append_scrape_snapshot(self, result: ReviewScrapeResult) -> str:
        record = ReviewScrapeResultCodec.to_record(result)
        record.snapshot_event_id = record.snapshot_event_id or str(uuid4())
        return await self._connection.insert_review_scrape_record(record)

    async def create_sitemap_crawl_run(
        self,
        *,
        retailer_name: str,
        entrypoint_url: str,
    ) -> str:
        record = SitemapCrawlRunRecord(
            retailer_name=retailer_name,
            entrypoint_url=entrypoint_url,
            status=SitemapCrawlRunStatus.RUNNING.value,
        )

        def _insert(session):
            session.add(record)
            session.flush()
            return record.crawl_run_id

        return await self._connection.run_session(_insert)

    async def finalize_sitemap_crawl_run(
        self,
        *,
        crawl_run_id: str,
        result: SitemapPdpDiscoveryResult,
    ) -> str:
        def _update(session):
            record = session.get(SitemapCrawlRunRecord, crawl_run_id)
            if record is None:
                raise RuntimeError(f"Missing sitemap crawl run: {crawl_run_id}")
            record.processed_sitemaps_count = len(result.processed_sitemaps)
            record.skipped_sitemaps_count = len(result.skipped_sitemaps)
            record.discovered_url_count = len(result.pdp_urls)
            record.error_count = len(result.errors)
            record.completed_at = self._new_york_now_naive()
            record.status = (
                SitemapCrawlRunStatus.COMPLETED_WITH_ERRORS.value
                if result.errors
                else SitemapCrawlRunStatus.COMPLETED.value
            )
            session.flush()
            return record.crawl_run_id

        return await self._connection.run_session(_update)

    async def fail_sitemap_crawl_run(
        self,
        *,
        crawl_run_id: str,
        result: SitemapPdpDiscoveryResult | None = None,
    ) -> str:
        def _update(session):
            record = session.get(SitemapCrawlRunRecord, crawl_run_id)
            if record is None:
                raise RuntimeError(f"Missing sitemap crawl run: {crawl_run_id}")
            if result is not None:
                record.processed_sitemaps_count = len(result.processed_sitemaps)
                record.skipped_sitemaps_count = len(result.skipped_sitemaps)
                record.discovered_url_count = len(result.pdp_urls)
                record.error_count = len(result.errors)
            record.completed_at = self._new_york_now_naive()
            record.status = SitemapCrawlRunStatus.FAILED.value
            session.flush()
            return record.crawl_run_id

        return await self._connection.run_session(_update)

    async def upsert_sitemap_crawl_records(
        self,
        *,
        crawl_run_id: str,
        retailer_name: str,
        records: list[SitemapCrawlRecordObservation],
    ) -> dict[str, int]:
        observed_at = self._new_york_now_naive()

        def _upsert(session):
            inserted_count = 0
            updated_count = 0
            unchanged_count = 0
            existing_records: dict[str, SitemapCrawlRecord] = {}
            record_urls = [record.record_url for record in records]
            chunk_size = 1000
            for chunk_start in range(0, len(record_urls), chunk_size):
                chunk_urls = record_urls[chunk_start : chunk_start + chunk_size]
                chunk_records = (
                    session.execute(
                        select(SitemapCrawlRecord).where(
                            SitemapCrawlRecord.retailer_name == retailer_name,
                            SitemapCrawlRecord.record_url.in_(chunk_urls),
                        )
                    )
                    .scalars()
                    .all()
                )
                existing_records.update(
                    {record.record_url: record for record in chunk_records}
                )

            for observation in records:
                record = existing_records.get(observation.record_url)
                if record is None:
                    record = SitemapCrawlRecord(
                        retailer_name=retailer_name,
                        record_url=observation.record_url,
                        parent_url=observation.parent_url,
                        record_type=observation.record_type,
                        url_type=observation.url_type,
                        depth=observation.depth,
                        first_encountered_at=observed_at,
                        latest_encountered_at=observed_at,
                        times_seen=1,
                        first_crawl_run_id=crawl_run_id,
                        last_crawl_run_id=crawl_run_id,
                        record_status=observation.record_status,
                        skip_reason=observation.skip_reason,
                        child_sitemap_count=observation.child_sitemap_count,
                        child_url_count=observation.child_url_count,
                        last_error_message=observation.last_error_message,
                    )
                    session.add(record)
                    existing_records[observation.record_url] = record
                    inserted_count += 1
                else:
                    state_changed = any(
                        [
                            record.parent_url != observation.parent_url,
                            record.record_type != observation.record_type,
                            record.url_type != observation.url_type,
                            record.depth != observation.depth,
                            record.record_status != observation.record_status,
                            record.skip_reason != observation.skip_reason,
                            record.child_sitemap_count
                            != observation.child_sitemap_count,
                            record.child_url_count != observation.child_url_count,
                            record.last_error_message != observation.last_error_message,
                        ]
                    )
                    record.parent_url = observation.parent_url
                    record.record_type = observation.record_type
                    record.url_type = observation.url_type
                    record.depth = observation.depth
                    record.latest_encountered_at = observed_at
                    record.times_seen += 1
                    record.last_crawl_run_id = crawl_run_id
                    record.record_status = observation.record_status
                    record.skip_reason = observation.skip_reason
                    record.child_sitemap_count = observation.child_sitemap_count
                    record.child_url_count = observation.child_url_count
                    record.last_error_message = observation.last_error_message
                    if state_changed:
                        updated_count += 1
                    else:
                        unchanged_count += 1

            session.flush()
            return {
                "inserted_record_count": inserted_count,
                "updated_record_count": updated_count,
                "unchanged_record_count": unchanged_count,
                "touched_record_count": inserted_count
                + updated_count
                + unchanged_count,
            }

        return await self._connection.run_session(_upsert)

    def _new_york_now_naive(self) -> datetime:
        return datetime.now(self.NEW_YORK_TZ).replace(tzinfo=None)

    async def get_latest_snapshot(self, product_url: str) -> ReviewScrapeResult | None:
        record = await self._connection.run_session(
            lambda session: session.execute(
                select(ReviewScrapeRecord)
                .where(ReviewScrapeRecord.product_url == product_url)
                .order_by(desc(ReviewScrapeRecord.scraped_at))
                .limit(1)
            ).scalar_one_or_none()
        )
        if not record:
            return None
        return ReviewScrapeResultCodec.from_record(record)

    async def list_snapshots(
        self, product_url: str, limit: int = 10
    ) -> list[ReviewScrapeResult]:
        records = await self._connection.run_session(
            lambda session: (
                session.execute(
                    select(ReviewScrapeRecord)
                    .where(ReviewScrapeRecord.product_url == product_url)
                    .order_by(desc(ReviewScrapeRecord.scraped_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        )
        return [ReviewScrapeResultCodec.from_record(record) for record in records]

    async def _safe_table_exists(self, table_name: str) -> bool | None:
        try:
            return await self._connection.has_table(table_name)
        except Exception:
            return None

    async def _list_accessible_databases(self) -> list[str]:
        try:
            return await self._connection.list_databases()
        except Exception:
            return []

    async def _list_accessible_schemas(self, database_name: str) -> list[str]:
        try:
            return await self._connection.list_schemas(database_name)
        except Exception:
            return []

    async def _list_accessible_tables(
        self, database_name: str, schema_name: str
    ) -> list[str]:
        try:
            return await self._connection.list_tables(database_name, schema_name)
        except Exception:
            return []

    async def _safe_grants_to_current_role(self) -> list[dict[str, Any]]:
        try:
            return await self._connection.show_grants_to_current_role()
        except Exception:
            return []

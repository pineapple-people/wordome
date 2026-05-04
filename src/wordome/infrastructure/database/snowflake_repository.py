from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import desc, func, select, update

from wordome.domain.reviews.models import ReviewScrapeResult
from wordome.domain.sitemaps import (
    SitemapCrawlRecordObservation,
    SitemapPdpDiscoveryResult,
)
from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeEntryRecord,
    ReviewScrapeQueueRecord,
    ReviewScrapeQueueStatus,
    ReviewScrapeRecord,
    ReviewScrapeRunRecord,
    ReviewScrapeRunStatus,
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

T = TypeVar("T")


class SnowflakeRepository:
    """
    Business logic for Snowflake persistence via SQLAlchemy ORM.
    """

    REVIEW_SCRAPES_TABLE = ReviewScrapeRecord.__tablename__
    REVIEW_SCRAPE_QUEUE_TABLE = ReviewScrapeQueueRecord.__tablename__
    REVIEW_SCRAPE_PIPELINE_RUNS_TABLE = ReviewScrapeRunRecord.__tablename__
    SITEMAP_CRAWL_RUNS_TABLE = SitemapCrawlRunRecord.__tablename__
    SITEMAP_CRAWL_RECORDS_TABLE = SitemapCrawlRecord.__tablename__
    REVIEW_SCRAPE_RECORDS_TABLE = ReviewScrapeEntryRecord.__tablename__
    NEW_YORK_TZ = ZoneInfo("America/New_York")

    def __init__(self, connection: SnowflakeConnection | None = None):
        self._connection = connection or SnowflakeConnection()
        self._config = get_snowflake_profile() if connection is None else None

    @staticmethod
    def _iter_batches(items: list[T], batch_size: int = 1000) -> Iterator[list[T]]:
        for batch_start in range(0, len(items), batch_size):
            yield items[batch_start : batch_start + batch_size]

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
            "review_scrape_queue_table": self.REVIEW_SCRAPE_QUEUE_TABLE,
            "review_scrape_pipeline_runs_table": self.REVIEW_SCRAPE_PIPELINE_RUNS_TABLE,
            "sitemap_crawl_runs_table": self.SITEMAP_CRAWL_RUNS_TABLE,
            "sitemap_crawl_records_table": self.SITEMAP_CRAWL_RECORDS_TABLE,
            "review_scrape_records_table": self.REVIEW_SCRAPE_RECORDS_TABLE,
            "current_context": None,
            "database_visible": None,
            "schema_visible": None,
            "review_scrapes_table_exists": None,
            "review_scrape_queue_table_exists": None,
            "review_scrape_pipeline_runs_table_exists": None,
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
            queue_table_exists = await self._safe_table_exists(
                ReviewScrapeQueueRecord.__tablename__
            )
            run_table_exists = await self._safe_table_exists(
                ReviewScrapeRunRecord.__tablename__
            )
            state_table_exists = await self._safe_table_exists(
                ReviewScrapeEntryRecord.__tablename__
            )
            result["review_scrapes_table_exists"] = history_table_exists
            result["review_scrape_queue_table_exists"] = queue_table_exists
            result["review_scrape_pipeline_runs_table_exists"] = run_table_exists
            result["review_scrape_records_table_exists"] = state_table_exists
            result["can_bootstrap_schema"] = (
                history_table_exists
                and queue_table_exists
                and run_table_exists
                and state_table_exists
            )
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
            history_table_exists = await self._safe_table_exists(
                ReviewScrapeRecord.__tablename__
            )
            queue_table_exists = await self._safe_table_exists(
                ReviewScrapeQueueRecord.__tablename__
            )
            run_table_exists = await self._safe_table_exists(
                ReviewScrapeRunRecord.__tablename__
            )
            state_table_exists = await self._safe_table_exists(
                ReviewScrapeEntryRecord.__tablename__
            )
            result["review_scrapes_table_exists"] = history_table_exists
            result["review_scrape_queue_table_exists"] = queue_table_exists
            result["review_scrape_pipeline_runs_table_exists"] = run_table_exists
            result["review_scrape_records_table_exists"] = state_table_exists
            result["can_bootstrap_schema"] = (
                history_table_exists
                and queue_table_exists
                and run_table_exists
                and state_table_exists
            )
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

    async def get_sitemap_crawl_run(self, crawl_run_id: str) -> dict[str, Any] | None:
        record = await self._connection.run_session(
            lambda session: session.get(SitemapCrawlRunRecord, crawl_run_id)
        )
        if record is None:
            return None
        return {
            "crawl_run_id": record.crawl_run_id,
            "retailer_name": record.retailer_name,
            "entrypoint_url": record.entrypoint_url,
            "status": record.status,
            "processed_sitemaps_count": record.processed_sitemaps_count,
            "skipped_sitemaps_count": record.skipped_sitemaps_count,
            "discovered_url_count": record.discovered_url_count,
            "error_count": record.error_count,
            "started_at": record.started_at.isoformat()
            if record.started_at is not None
            else None,
            "completed_at": record.completed_at.isoformat()
            if record.completed_at is not None
            else None,
        }

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

    async def create_review_scrape_run(
        self,
        *,
        retailer_name: str,
        trigger_type: str,
        selected_url_count: int = 0,
    ) -> str:
        record = ReviewScrapeRunRecord(
            retailer_name=retailer_name,
            trigger_type=trigger_type,
            status=ReviewScrapeRunStatus.RUNNING.value,
            selected_url_count=selected_url_count,
        )

        def _insert(session):
            session.add(record)
            session.flush()
            return record.review_scrape_run_id

        return await self._connection.run_session(_insert)

    async def update_review_scrape_run_selected_count(
        self,
        *,
        review_scrape_run_id: str,
        selected_url_count: int,
    ) -> str:
        def _update(session):
            record = session.get(ReviewScrapeRunRecord, review_scrape_run_id)
            if record is None:
                raise RuntimeError(f"Missing review scrape run: {review_scrape_run_id}")
            record.selected_url_count = selected_url_count
            session.flush()
            return record.review_scrape_run_id

        return await self._connection.run_session(_update)

    async def enqueue_review_scrape_urls(
        self,
        *,
        retailer_name: str,
        product_urls: list[str],
        batch_progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> dict[str, int]:
        if not product_urls:
            return {
                "inserted_queue_record_count": 0,
                "existing_queue_record_count": 0,
                "touched_queue_record_count": 0,
            }

        unique_product_urls = list(dict.fromkeys(product_urls))
        observed_at = self._new_york_now_naive()

        def _upsert_batch(session, product_url_batch: list[str]):
            existing_records: dict[str, ReviewScrapeQueueRecord] = {}
            chunk_records = (
                session.execute(
                    select(ReviewScrapeQueueRecord).where(
                        ReviewScrapeQueueRecord.retailer_name == retailer_name,
                        ReviewScrapeQueueRecord.product_url.in_(product_url_batch),
                    )
                )
                .scalars()
                .all()
            )
            existing_records.update(
                {record.product_url: record for record in chunk_records}
            )

            inserted_count = 0
            existing_count = 0
            for product_url in product_url_batch:
                existing_record = existing_records.get(product_url)
                if existing_record is not None:
                    existing_count += 1
                    continue
                session.add(
                    ReviewScrapeQueueRecord(
                        retailer_name=retailer_name,
                        product_url=product_url,
                        queue_status=ReviewScrapeQueueStatus.UNCLAIMED.value,
                        attempt_count=0,
                        latest_review_scrape_run_id=None,
                        latest_error_message=None,
                        enqueued_at=observed_at,
                        updated_at=observed_at,
                    )
                )
                inserted_count += 1

            session.flush()
            return {
                "inserted_queue_record_count": inserted_count,
                "existing_queue_record_count": existing_count,
                "touched_queue_record_count": inserted_count + existing_count,
            }

        totals = {
            "inserted_queue_record_count": 0,
            "existing_queue_record_count": 0,
            "touched_queue_record_count": 0,
        }
        product_url_batches = list(self._iter_batches(unique_product_urls))
        total_batches = len(product_url_batches)
        for batch_index, product_url_batch in enumerate(product_url_batches, start=1):
            if batch_progress_callback is not None:
                batch_progress_callback(
                    batch_index,
                    total_batches,
                    len(product_url_batch),
                )
            batch_counts = await self._connection.run_session(
                lambda session, batch=product_url_batch: _upsert_batch(session, batch)
            )
            for key, value in batch_counts.items():
                totals[key] += value
        return totals

    async def claim_review_scrape_queue_urls(
        self,
        *,
        retailer_name: str,
        limit: int = 10,
        review_scrape_run_id: str,
    ) -> list[str]:
        observed_at = self._new_york_now_naive()

        def _claim(session):
            candidate_urls = list(
                session.execute(
                    select(ReviewScrapeQueueRecord.product_url)
                    .where(
                        ReviewScrapeQueueRecord.retailer_name == retailer_name,
                        ReviewScrapeQueueRecord.queue_status
                        == ReviewScrapeQueueStatus.UNCLAIMED.value,
                    )
                    .order_by(
                        ReviewScrapeQueueRecord.attempt_count.asc(),
                        ReviewScrapeQueueRecord.updated_at.asc(),
                        ReviewScrapeQueueRecord.enqueued_at.asc(),
                        ReviewScrapeQueueRecord.product_url.asc(),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            if not candidate_urls:
                return []

            session.execute(
                update(ReviewScrapeQueueRecord)
                .where(
                    ReviewScrapeQueueRecord.retailer_name == retailer_name,
                    ReviewScrapeQueueRecord.product_url.in_(candidate_urls),
                    ReviewScrapeQueueRecord.queue_status
                    == ReviewScrapeQueueStatus.UNCLAIMED.value,
                )
                .values(
                    queue_status=ReviewScrapeQueueStatus.CLAIMED.value,
                    attempt_count=ReviewScrapeQueueRecord.attempt_count + 1,
                    latest_review_scrape_run_id=review_scrape_run_id,
                    latest_error_message=None,
                    updated_at=observed_at,
                )
            )
            session.flush()
            return list(
                session.execute(
                    select(ReviewScrapeQueueRecord.product_url)
                    .where(
                        ReviewScrapeQueueRecord.retailer_name == retailer_name,
                        ReviewScrapeQueueRecord.latest_review_scrape_run_id
                        == review_scrape_run_id,
                        ReviewScrapeQueueRecord.queue_status
                        == ReviewScrapeQueueStatus.CLAIMED.value,
                        ReviewScrapeQueueRecord.updated_at == observed_at,
                    )
                    .order_by(ReviewScrapeQueueRecord.product_url.asc())
                )
                .scalars()
                .all()
            )

        for _ in range(3):
            claimed_urls = await self._connection.run_session(_claim)
            if claimed_urls or limit <= 0:
                return claimed_urls
        return []

    async def list_review_scrape_queue_records(
        self,
        *,
        retailer_name: str | None = None,
        queue_status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        def _select(session):
            statement = select(ReviewScrapeQueueRecord)
            if retailer_name is not None:
                statement = statement.where(
                    ReviewScrapeQueueRecord.retailer_name == retailer_name
                )
            if queue_status is not None:
                statement = statement.where(
                    ReviewScrapeQueueRecord.queue_status == queue_status
                )
            total_count = session.execute(
                select(func.count()).select_from(statement.subquery())
            ).scalar_one()
            records = (
                session.execute(
                    statement.order_by(
                        ReviewScrapeQueueRecord.updated_at.desc(),
                        ReviewScrapeQueueRecord.enqueued_at.desc(),
                        ReviewScrapeQueueRecord.product_url.asc(),
                    ).limit(limit)
                )
                .scalars()
                .all()
            )
            return {
                "item_count_total": total_count,
                "items": [
                    {
                        "retailer_name": record.retailer_name,
                        "product_url": record.product_url,
                        "queue_status": record.queue_status,
                        "attempt_count": record.attempt_count,
                        "latest_review_scrape_run_id": (
                            record.latest_review_scrape_run_id
                        ),
                        "latest_error_message": record.latest_error_message,
                        "enqueued_at": record.enqueued_at.isoformat()
                        if record.enqueued_at is not None
                        else None,
                        "updated_at": record.updated_at.isoformat()
                        if record.updated_at is not None
                        else None,
                    }
                    for record in records
                ],
            }

        return await self._connection.run_session(_select)

    async def summarize_review_scrape_queue(
        self,
        *,
        retailer_name: str | None = None,
    ) -> dict[str, Any]:
        def _select(session):
            statement = select(
                ReviewScrapeQueueRecord.queue_status,
                func.count().label("row_count"),
            )
            if retailer_name is not None:
                statement = statement.where(
                    ReviewScrapeQueueRecord.retailer_name == retailer_name
                )
            rows = session.execute(
                statement.group_by(ReviewScrapeQueueRecord.queue_status)
            ).all()
            counts_by_status = {
                ReviewScrapeQueueStatus.UNCLAIMED.value: 0,
                ReviewScrapeQueueStatus.CLAIMED.value: 0,
                ReviewScrapeQueueStatus.COMPLETED.value: 0,
            }
            for queue_status_value, row_count in rows:
                counts_by_status[queue_status_value] = row_count
            return {
                "retailer_name": retailer_name,
                "total_count": sum(counts_by_status.values()),
                "counts_by_status": counts_by_status,
            }

        return await self._connection.run_session(_select)

    async def record_review_scrape_queue_failure(
        self,
        *,
        retailer_name: str,
        product_url: str,
        latest_error_message: str,
    ) -> None:
        observed_at = self._new_york_now_naive()

        def _update(session):
            record = session.get(
                ReviewScrapeQueueRecord,
                (retailer_name, product_url),
            )
            if record is None:
                raise RuntimeError(
                    "Missing review scrape queue record: "
                    f"{retailer_name=} {product_url=}"
                )
            record.queue_status = ReviewScrapeQueueStatus.UNCLAIMED.value
            record.latest_error_message = latest_error_message
            record.updated_at = observed_at
            session.flush()

        await self._connection.run_session(_update)

    async def mark_review_scrape_queue_completed(
        self,
        *,
        retailer_name: str,
        product_url: str,
    ) -> None:
        observed_at = self._new_york_now_naive()

        def _update(session):
            record = session.get(
                ReviewScrapeQueueRecord,
                (retailer_name, product_url),
            )
            if record is None:
                raise RuntimeError(
                    "Missing review scrape queue record: "
                    f"{retailer_name=} {product_url=}"
                )
            record.queue_status = ReviewScrapeQueueStatus.COMPLETED.value
            record.latest_error_message = None
            record.updated_at = observed_at
            session.flush()

        await self._connection.run_session(_update)

    async def finalize_review_scrape_run(
        self,
        *,
        review_scrape_run_id: str,
        success_count: int,
        failure_count: int,
    ) -> str:
        def _update(session):
            record = session.get(ReviewScrapeRunRecord, review_scrape_run_id)
            if record is None:
                raise RuntimeError(f"Missing review scrape run: {review_scrape_run_id}")
            record.success_count = success_count
            record.failure_count = failure_count
            record.completed_at = self._new_york_now_naive()
            record.status = (
                ReviewScrapeRunStatus.COMPLETED_WITH_ERRORS.value
                if failure_count > 0
                else ReviewScrapeRunStatus.COMPLETED.value
            )
            session.flush()
            return record.review_scrape_run_id

        return await self._connection.run_session(_update)

    async def fail_review_scrape_run(
        self,
        *,
        review_scrape_run_id: str,
        success_count: int = 0,
        failure_count: int = 0,
    ) -> str:
        def _update(session):
            record = session.get(ReviewScrapeRunRecord, review_scrape_run_id)
            if record is None:
                raise RuntimeError(f"Missing review scrape run: {review_scrape_run_id}")
            record.success_count = success_count
            record.failure_count = failure_count
            record.completed_at = self._new_york_now_naive()
            record.status = ReviewScrapeRunStatus.FAILED.value
            session.flush()
            return record.review_scrape_run_id

        return await self._connection.run_session(_update)

    async def upsert_sitemap_crawl_records(
        self,
        *,
        crawl_run_id: str,
        retailer_name: str,
        records: list[SitemapCrawlRecordObservation],
        batch_progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> dict[str, int]:
        if not records:
            return {
                "inserted_record_count": 0,
                "updated_record_count": 0,
                "unchanged_record_count": 0,
                "touched_record_count": 0,
            }

        observed_at = self._new_york_now_naive()

        def _upsert_batch(
            session,
            record_batch: list[SitemapCrawlRecordObservation],
        ):
            inserted_count = 0
            updated_count = 0
            unchanged_count = 0
            existing_records: dict[str, SitemapCrawlRecord] = {}
            record_urls = [record.record_url for record in record_batch]
            chunk_records = (
                session.execute(
                    select(SitemapCrawlRecord).where(
                        SitemapCrawlRecord.retailer_name == retailer_name,
                        SitemapCrawlRecord.record_url.in_(record_urls),
                    )
                )
                .scalars()
                .all()
            )
            existing_records.update(
                {record.record_url: record for record in chunk_records}
            )

            for observation in record_batch:
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

        totals = {
            "inserted_record_count": 0,
            "updated_record_count": 0,
            "unchanged_record_count": 0,
            "touched_record_count": 0,
        }
        record_batches = list(self._iter_batches(records))
        total_batches = len(record_batches)
        for batch_index, record_batch in enumerate(record_batches, start=1):
            if batch_progress_callback is not None:
                batch_progress_callback(
                    batch_index,
                    total_batches,
                    len(record_batch),
                )
            batch_counts = await self._connection.run_session(
                lambda session, batch=record_batch: _upsert_batch(session, batch)
            )
            for key, value in batch_counts.items():
                totals[key] += value
        return totals

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

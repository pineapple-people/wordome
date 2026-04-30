from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select

from wordome.domain.reviews.models import ReviewScrapeResult
from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeRecord,
    eastern_now,
)
from wordome.infrastructure.database.review_scrape_result_codec import (
    ReviewScrapeResultCodec,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_config
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


class SnowflakeRepository:
    """
    Business logic for Snowflake persistence via SQLAlchemy ORM.
    """

    REVIEW_SCRAPES_TABLE = ReviewScrapeRecord.__tablename__

    def __init__(self, connection: SnowflakeConnection | None = None):
        self._connection = connection or SnowflakeConnection()
        self._config = get_snowflake_config() if connection is None else None

    async def is_connected(self) -> bool:
        return await self._connection.is_connected()

    async def get_repository_health(self) -> dict[str, Any]:
        is_connected = await self.is_connected()
        result: dict[str, Any] = {
            "database_connected": is_connected,
            "service": "wordome",
            "timestamp": datetime.now(UTC).isoformat(),
            "configured_database": self._config.database if self._config else None,
            "configured_schema": self._config.schema if self._config else None,
            "review_scrapes_table": self.REVIEW_SCRAPES_TABLE,
            "current_context": None,
            "database_visible": None,
            "schema_visible": None,
            "review_scrapes_table_exists": None,
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
            table_exists = await self._safe_table_exists()
            result["review_scrapes_table_exists"] = table_exists
            result["can_bootstrap_schema"] = table_exists
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
            result["schema_visible"] = self._config.schema in accessible_schemas
        else:
            result["errors"].append(
                f"Configured database '{self._config.database}' is not visible."
            )

        if result["database_visible"] and result["schema_visible"]:
            result[
                "accessible_tables_in_configured_schema"
            ] = await self._list_accessible_tables(
                self._config.database,
                self._config.schema,
            )
            table_exists = await self._safe_table_exists()
            result["review_scrapes_table_exists"] = table_exists
            result["can_bootstrap_schema"] = True
        elif result["database_visible"]:
            result["errors"].append(
                f"Configured schema '{self._config.schema}' is not visible in database "
                f"'{self._config.database}'."
            )

        result["grants_to_current_role"] = await self._safe_grants_to_current_role()
        return result

    async def append_scrape_snapshot(self, result: ReviewScrapeResult) -> str:
        record = ReviewScrapeResultCodec.to_record(result)
        record.snapshot_event_id = record.snapshot_event_id or str(uuid4())
        record.scraped_at = record.scraped_at or eastern_now()
        return await self._connection.insert_review_scrape_record(record)

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

    async def _safe_table_exists(self) -> bool | None:
        try:
            return await self._connection.has_table(ReviewScrapeRecord.__tablename__)
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

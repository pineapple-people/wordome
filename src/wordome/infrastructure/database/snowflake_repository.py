from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select, text

from wordome.domain.reviews.models import ReviewScrapeResult
from wordome.infrastructure.database.review_scrape_orm import ReviewScrapeRecord
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

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _is_safe_rename_noop(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "does not exist" in message
            or "invalid identifier" in message
            or "already exists" in message
        )

    async def is_connected(self) -> bool:
        return await self._connection.is_connected()

    async def get_repository_health(self) -> dict[str, Any]:
        is_connected = await self.is_connected()
        result: dict[str, Any] = {
            "database_connected": is_connected,
            "service": "wordome",
            "timestamp": datetime.utcnow().isoformat(),
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

    async def bootstrap_database_and_schema(
        self, *, include_tables: bool = True
    ) -> dict[str, Any]:
        if self._config is None:
            raise RuntimeError("Bootstrapping requires a configured Snowflake target.")

        quoted_database = self._quote_identifier(self._config.database)
        quoted_schema = self._quote_identifier(self._config.schema)

        await self._connection.run_session(
            lambda session: session.execute(
                text(f"CREATE DATABASE IF NOT EXISTS {quoted_database}")
            )
        )
        await self._connection.run_session(
            lambda session: session.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {quoted_database}.{quoted_schema}")
            )
        )

        tables_created = False
        if include_tables:
            await self.ensure_schema()
            tables_created = True

        return {
            "success": True,
            "database": self._config.database,
            "schema": self._config.schema,
            "tables_created": tables_created,
            "review_scrapes_table": self.REVIEW_SCRAPES_TABLE,
        }

    async def ensure_schema(self) -> None:
        try:
            await self._connection.create_all()
            if self._config is not None:
                await self._align_review_scrapes_table_schema()
        except Exception as exc:
            raise RuntimeError(
                "Failed to ensure the review_scrapes persistence schema is aligned. "
                "Run the Snowflake bootstrap/alignment path and inspect the underlying "
                f"database error. Original error: {exc}"
            ) from exc

    async def append_scrape_snapshot(self, result: ReviewScrapeResult) -> str:
        await self.ensure_schema()
        record = ReviewScrapeResultCodec.to_record(result)
        record.snapshot_event_id = record.snapshot_event_id or str(uuid4())
        record.scraped_at = record.scraped_at or datetime.utcnow()
        return await self._connection.insert_review_scrape_record(record)

    async def get_latest_snapshot(self, product_url: str) -> ReviewScrapeResult | None:
        await self.ensure_schema()
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
        await self.ensure_schema()
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

    async def _align_review_scrapes_table_schema(self) -> None:
        if self._config is None:
            return
        quoted_database = self._quote_identifier(self._config.database)
        quoted_schema = self._quote_identifier(self._config.schema)
        table_name = f"{quoted_database}.{quoted_schema}.{self.REVIEW_SCRAPES_TABLE}"
        try:
            await self._connection.run_session(
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
            if not self._is_safe_rename_noop(exc):
                raise RuntimeError(
                    "Failed to rename legacy column 'snapshot_id' to "
                    f"'snapshot_event_id' on {table_name}. Original error: {exc}"
                ) from exc

        try:
            await self._connection.run_session(
                lambda session: session.execute(
                    text(
                        f"""
                        ALTER TABLE {table_name}
                        ADD COLUMN IF NOT EXISTS snapshot_hash STRING
                        """
                    )
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to add or verify 'snapshot_hash' on {table_name}. "
                f"Original error: {exc}"
            ) from exc

        try:
            await self._connection.run_session(
                lambda session: session.execute(
                    text(
                        f"""
                        UPDATE {table_name}
                        SET snapshot_hash = COALESCE(
                            snapshot_hash,
                            SHA2(
                                TO_JSON(
                                    OBJECT_CONSTRUCT_KEEP_NULL(
                                        'product_url', product_url,
                                        'review_page_url', review_page_url,
                                        'reviews_count', reviews_count,
                                        'metadata', metadata,
                                        'reviews', reviews
                                    )
                                ),
                                256
                            )
                        )
                        """
                    )
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to backfill 'snapshot_hash' values on {table_name}. "
                f"Original error: {exc}"
            ) from exc

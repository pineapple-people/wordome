import asyncio
import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from hashlib import sha256
from typing import Any, TypeVar

from snowflake.sqlalchemy import URL
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wordome.infrastructure.database.review_scrape_orm import (
    Base,
    ReviewScrapeEntryRecord,
    ReviewScrapeRecord,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_config

T = TypeVar("T")


class SnowflakeConnection:
    """SQLAlchemy engine and session management for Snowflake."""

    def __init__(self, engine: Engine | None = None):
        self._config = None
        if engine is not None:
            self._set_table_schema(None)
            self._engine = engine
        else:
            self._config = get_snowflake_config()
            qualified_schema = f"{self._config.database}.{self._config.schema}"
            self._set_table_schema(qualified_schema)
            self._engine = create_engine(
                URL(
                    account=self._config.account,
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database,
                    schema=self._config.schema,
                    warehouse=self._config.warehouse,
                )
            )
        self._insert_review_scrape_record = (
            self._insert_review_scrape_record_snowflake
            if self._engine.dialect.name == "snowflake"
            else self._insert_review_scrape_record_orm
        )
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    @staticmethod
    def _set_table_schema(schema: str | None) -> None:
        for table in Base.metadata.tables.values():
            table.schema = schema

    async def _run(self, fn, *args, **kwargs):
        """Run blocking SQLAlchemy work in a worker thread."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    @asynccontextmanager
    async def get_session(self):
        """Yield a SQLAlchemy session bound to the Snowflake engine."""
        session = self._session_factory()
        try:
            yield session
        finally:
            await self._run(session.close)

    async def run_session(self, fn: Callable[[Session], T]) -> T:
        """Execute session work in a thread and commit on success."""

        def _run_in_session() -> T:
            session = self._session_factory()
            try:
                result = fn(session)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return await self._run(_run_in_session)

    async def create_all(self) -> None:
        await self._run(lambda: Base.metadata.create_all(self._engine))

    async def insert_review_scrape_record(self, record: ReviewScrapeRecord) -> str:
        return await self.run_session(
            lambda session: self._insert_review_scrape_record(session, record)
        )

    async def get_current_context(self) -> dict[str, Any]:
        row = await self.run_session(
            lambda session: session.execute(
                text(
                    """
                    SELECT
                        CURRENT_ACCOUNT(),
                        CURRENT_USER(),
                        CURRENT_ROLE(),
                        CURRENT_WAREHOUSE(),
                        CURRENT_DATABASE(),
                        CURRENT_SCHEMA()
                    """
                )
            ).one()
        )
        return {
            "account": row[0],
            "user": row[1],
            "role": row[2],
            "warehouse": row[3],
            "database": row[4],
            "schema": row[5],
        }

    async def list_databases(self) -> list[str]:
        rows = await self.run_session(
            lambda session: session.execute(text("SHOW DATABASES")).all()
        )
        return sorted({row[1] for row in rows if len(row) > 1})

    async def list_schemas(self, database_name: str) -> list[str]:
        rows = await self.run_session(
            lambda session: session.execute(
                text(f"SHOW SCHEMAS IN DATABASE {database_name}")
            ).all()
        )
        return sorted({row[1] for row in rows if len(row) > 1})

    async def list_tables(self, database_name: str, schema_name: str) -> list[str]:
        rows = await self.run_session(
            lambda session: session.execute(
                text(f"SHOW TABLES IN SCHEMA {database_name}.{schema_name}")
            ).all()
        )
        return sorted({row[1] for row in rows if len(row) > 1})

    async def show_grants_to_current_role(self) -> list[dict[str, Any]]:
        context = await self.get_current_context()
        current_role = context.get("role")
        if not current_role:
            return []
        rows = await self.run_session(
            lambda session: session.execute(
                text(f"SHOW GRANTS TO ROLE {current_role}")
            ).all()
        )
        return [
            {
                "created_on": row[0],
                "privilege": row[1],
                "granted_on": row[2],
                "name": row[3],
                "granted_to": row[4],
                "grantee_name": row[5],
                "grant_option": row[6],
                "granted_by": row[7],
            }
            for row in rows
            if len(row) >= 8
        ]

    async def has_table(self, table_name: str) -> bool:
        schema = ReviewScrapeRecord.__table__.schema
        return await self._run(
            lambda: inspect(self._engine).has_table(
                table_name,
                schema=schema,
            )
        )

    async def is_connected(self) -> bool:
        """Pure technical check that the engine can establish a session."""
        try:
            await self.run_session(
                lambda session: session.execute(select(1)).scalar_one()
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _insert_review_scrape_record_orm(session, record: ReviewScrapeRecord) -> str:
        session.add(record)
        session.flush()
        for incoming_state in SnowflakeConnection._review_entry_states(record):
            state = session.get(
                ReviewScrapeEntryRecord,
                incoming_state.review_entry_id,
            )
            if state is None:
                session.add(incoming_state)
                continue
            state.product_url = incoming_state.product_url
            state.latest_snapshot_event_id = incoming_state.latest_snapshot_event_id
            state.review_page_url = incoming_state.review_page_url
            state.author = incoming_state.author
            state.title = incoming_state.title
            state.body = incoming_state.body
            state.rating = incoming_state.rating
            state.rating_scale_max = incoming_state.rating_scale_max
            state.review_date = incoming_state.review_date
            state.review_source = incoming_state.review_source
            state.source_url = incoming_state.source_url
            state.source_name = incoming_state.source_name
            state.pipeline_version = incoming_state.pipeline_version
            state.last_seen_at = datetime.now()
        session.flush()
        return record.snapshot_event_id

    @staticmethod
    def _insert_review_scrape_record_snowflake(
        session, record: ReviewScrapeRecord
    ) -> str:
        history_table_name = SnowflakeConnection._qualified_table_name(
            ReviewScrapeRecord.__table__
        )
        state_table_name = SnowflakeConnection._qualified_table_name(
            ReviewScrapeEntryRecord.__table__
        )
        payload = {
            "snapshot_event_id": record.snapshot_event_id,
            "snapshot_hash": record.snapshot_hash,
            "product_url": record.product_url,
            "review_page_url": record.review_page_url,
            "reviews_count": record.reviews_count,
            "source_name": record.source_name,
            "pipeline_version": record.pipeline_version,
            "metadata_json": json.dumps(record.metadata_payload),
            "reviews_json": json.dumps(record.reviews_payload),
            "review_entries_json": json.dumps(
                SnowflakeConnection._review_entry_payloads(record)
            ),
        }
        session.execute(
            text(
                f"""
                INSERT INTO {history_table_name} (
                    snapshot_event_id,
                    snapshot_hash,
                    product_url,
                    review_page_url,
                    reviews_count,
                    source_name,
                    pipeline_version,
                    metadata,
                    reviews
                )
                SELECT
                    :snapshot_event_id,
                    :snapshot_hash,
                    :product_url,
                    :review_page_url,
                    :reviews_count,
                    :source_name,
                    :pipeline_version,
                    PARSE_JSON(:metadata_json),
                    PARSE_JSON(:reviews_json)
                """
            ),
            payload,
        )
        session.execute(
            text(
                f"""
                MERGE INTO {state_table_name} target
                USING (
                    SELECT
                        value:review_entry_id::STRING AS review_entry_id,
                        value:product_url::STRING AS product_url,
                        value:first_snapshot_event_id::STRING
                            AS first_snapshot_event_id,
                        value:latest_snapshot_event_id::STRING
                            AS latest_snapshot_event_id,
                        value:review_page_url::STRING AS review_page_url,
                        value:author::STRING AS author,
                        value:title::STRING AS title,
                        value:body::STRING AS body,
                        value:rating::FLOAT AS rating,
                        value:rating_scale_max::INTEGER AS rating_scale_max,
                        value:review_date::STRING AS review_date,
                        value:review_source::STRING AS review_source,
                        value:source_url::STRING AS source_url,
                        value:source_name::STRING AS source_name,
                        value:pipeline_version::STRING AS pipeline_version,
                        CAST(
                            CONVERT_TIMEZONE(
                                'America/New_York',
                                CURRENT_TIMESTAMP()
                            ) AS TIMESTAMP_NTZ
                        ) AS state_seen_at
                    FROM TABLE(FLATTEN(input => PARSE_JSON(:review_entries_json)))
                ) source
                ON target.review_entry_id = source.review_entry_id
                WHEN MATCHED THEN UPDATE SET
                    product_url = source.product_url,
                    latest_snapshot_event_id = source.latest_snapshot_event_id,
                    review_page_url = source.review_page_url,
                    author = source.author,
                    title = source.title,
                    body = source.body,
                    rating = source.rating,
                    rating_scale_max = source.rating_scale_max,
                    review_date = source.review_date,
                    review_source = source.review_source,
                    source_url = source.source_url,
                    source_name = source.source_name,
                    pipeline_version = source.pipeline_version,
                    last_seen_at = source.state_seen_at
                WHEN NOT MATCHED THEN INSERT (
                    review_entry_id,
                    product_url,
                    first_snapshot_event_id,
                    latest_snapshot_event_id,
                    review_page_url,
                    author,
                    title,
                    body,
                    rating,
                    rating_scale_max,
                    review_date,
                    review_source,
                    source_url,
                    source_name,
                    pipeline_version,
                    first_seen_at,
                    last_seen_at
                ) VALUES (
                    source.review_entry_id,
                    source.product_url,
                    source.first_snapshot_event_id,
                    source.latest_snapshot_event_id,
                    source.review_page_url,
                    source.author,
                    source.title,
                    source.body,
                    source.rating,
                    source.rating_scale_max,
                    source.review_date,
                    source.review_source,
                    source.source_url,
                    source.source_name,
                    source.pipeline_version,
                    source.state_seen_at,
                    source.state_seen_at
                )
                """
            ),
            payload,
        )
        return record.snapshot_event_id

    @staticmethod
    def _qualified_table_name(table) -> str:
        return f"{table.schema}.{table.name}" if table.schema else table.name

    @staticmethod
    def _review_entry_states(
        record: ReviewScrapeRecord,
    ) -> list[ReviewScrapeEntryRecord]:
        return [
            ReviewScrapeEntryRecord(**payload)
            for payload in SnowflakeConnection._review_entry_payloads(record)
        ]

    @staticmethod
    def _review_entry_payloads(record: ReviewScrapeRecord) -> list[dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        for review_payload in record.reviews_payload:
            if not isinstance(review_payload, dict):
                continue
            payload = SnowflakeConnection._review_entry_payload(record, review_payload)
            payloads[payload["review_entry_id"]] = payload
        return list(payloads.values())

    @staticmethod
    def _review_entry_payload(
        record: ReviewScrapeRecord, review_payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "review_entry_id": SnowflakeConnection._review_entry_id(
                record.product_url, review_payload
            ),
            "product_url": record.product_url,
            "first_snapshot_event_id": record.snapshot_event_id,
            "latest_snapshot_event_id": record.snapshot_event_id,
            "review_page_url": record.review_page_url,
            "author": review_payload.get("author"),
            "title": review_payload.get("title"),
            "body": review_payload.get("body") or "",
            "rating": review_payload.get("rating"),
            "rating_scale_max": review_payload.get("rating_scale_max"),
            "review_date": review_payload.get("date"),
            "review_source": review_payload.get("source"),
            "source_url": review_payload.get("source_url"),
            "source_name": record.source_name,
            "pipeline_version": record.pipeline_version,
        }

    @staticmethod
    def _review_entry_id(product_url: str, review_payload: dict[str, Any]) -> str:
        identity_payload = {
            "product_url": product_url,
            "author": review_payload.get("author"),
            "title": review_payload.get("title"),
            "body": review_payload.get("body") or "",
            "rating": review_payload.get("rating"),
            "rating_scale_max": review_payload.get("rating_scale_max"),
            "date": review_payload.get("date"),
        }
        canonical = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

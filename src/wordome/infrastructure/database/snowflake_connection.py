import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from snowflake.sqlalchemy import URL
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wordome.infrastructure.database.review_scrape_orm import Base, ReviewScrapeRecord
from wordome.infrastructure.database.review_scrape_result_codec import (
    ReviewScrapeResultCodec,
)
from wordome.infrastructure.database.snowflake_config import get_snowflake_config

T = TypeVar("T")


class SnowflakeConnection:
    """SQLAlchemy engine and session management for Snowflake."""

    def __init__(self, engine: Engine | None = None):
        self._config = None
        if engine is not None:
            ReviewScrapeRecord.__table__.schema = None
            self._engine = engine
        else:
            self._config = get_snowflake_config()
            qualified_schema = f"{self._config.database}.{self._config.schema}"
            ReviewScrapeRecord.__table__.schema = qualified_schema
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
        return record.snapshot_event_id

    @staticmethod
    def _insert_review_scrape_record_snowflake(
        session, record: ReviewScrapeRecord
    ) -> str:
        table = ReviewScrapeRecord.__table__
        table_name = f"{table.schema}.{table.name}" if table.schema else table.name
        session.execute(
            text(
                f"""
                INSERT INTO {table_name} (
                    snapshot_event_id,
                    snapshot_hash,
                    product_url,
                    review_page_url,
                    reviews_count,
                    source_name,
                    pipeline_version,
                    metadata,
                    reviews,
                    scraped_at
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
                    PARSE_JSON(:reviews_json),
                    :scraped_at
                """
            ),
            {
                "snapshot_event_id": record.snapshot_event_id,
                "snapshot_hash": record.snapshot_hash,
                "product_url": record.product_url,
                "review_page_url": record.review_page_url,
                "reviews_count": record.reviews_count,
                "source_name": record.source_name,
                "pipeline_version": record.pipeline_version,
                "metadata_json": ReviewScrapeResultCodec.serialize_metadata_json(
                    record.metadata_payload
                ),
                "reviews_json": ReviewScrapeResultCodec.serialize_reviews_json(
                    record.reviews_payload
                ),
                "scraped_at": record.scraped_at,
            },
        )
        return record.snapshot_event_id

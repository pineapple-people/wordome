from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from snowflake.sqlalchemy import VARIANT
from sqlalchemy import DateTime, Float, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

payload_type = JSON().with_variant(VARIANT, "snowflake")


class Base(DeclarativeBase):
    pass


class ReviewScrapeRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ReviewScrapeRunTriggerType(StrEnum):
    CRAWL = "crawl"
    SINGLE = "single"


class ReviewScrapeQueueStatus(StrEnum):
    UNCLAIMED = "unclaimed"
    CLAIMED = "claimed"
    COMPLETED = "completed"


class ReviewScrapeRunRecord(Base):
    # TODO: Consider renaming table to `review_scrape_runs` in a future schema
    # cleanup pass once downstream usage is ready for the migration.
    __tablename__ = "review_scrape_pipeline_runs"

    review_scrape_run_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique identifier for one review scrape pipeline execution.",
    )
    retailer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Retailer/profile key used for the review scrape run.",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Expected values: crawl, single.",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewScrapeRunStatus.RUNNING.value,
        comment=("Expected values: running, completed, completed_with_errors, failed."),
    )
    selected_url_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of PDP URLs selected for processing in this run.",
    )
    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of PDP URLs successfully scraped in this run.",
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of PDP URLs that failed during this run.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="Set when the review scrape run reaches a terminal status.",
    )


class ReviewScrapeQueueRecord(Base):
    __tablename__ = "review_scrape_queue"

    retailer_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Retailer/profile key that owns this queued PDP URL.",
    )
    product_url: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        comment="Queued PDP URL awaiting successful review scraping.",
    )
    queue_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewScrapeQueueStatus.UNCLAIMED.value,
        comment="Expected values: unclaimed, claimed, completed.",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of review scrape attempts made while this URL was queued.",
    )
    latest_review_scrape_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Most recent review scrape pipeline run that touched this queued URL.",
    )
    latest_error_message: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Most recent error message recorded while this URL remained queued.",
    )
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
        comment="Time this PDP URL was first inserted into the review scrape queue.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
        comment="Time queue metadata was last updated for this PDP URL.",
    )


class ReviewScrapeRecord(Base):
    # TODO: Consider renaming table to `review_scrape_snapshots` in a future
    # schema cleanup pass once downstream usage is ready for the migration.
    __tablename__ = "review_scrapes"

    snapshot_event_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    review_page_url: Mapped[str | None] = mapped_column(String, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="reviews_scraper_ikea",
    )
    pipeline_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="v1",
    )
    metadata_payload: Mapped[dict] = mapped_column(
        "metadata", payload_type, nullable=False
    )
    reviews_payload: Mapped[list] = mapped_column(
        "reviews", payload_type, nullable=False
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
    )


class ReviewScrapeEntryRecord(Base):
    # TODO: Consider renaming table to `review_entry_records` in a future
    # schema cleanup pass once downstream usage is ready for the migration.
    __tablename__ = "review_scrape_records"

    review_entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    first_snapshot_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    latest_snapshot_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    review_page_url: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_scale_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_date: Mapped[str | None] = mapped_column(String, nullable=True)
    review_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(
            "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) "
            "AS TIMESTAMP_NTZ)"
        ),
    )

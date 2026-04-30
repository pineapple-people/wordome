from datetime import datetime
from uuid import uuid4

from snowflake.sqlalchemy import VARIANT
from sqlalchemy import DateTime, Float, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

payload_type = JSON().with_variant(VARIANT, "snowflake")


class Base(DeclarativeBase):
    pass


class ReviewScrapeRecord(Base):
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

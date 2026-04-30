from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from snowflake.sqlalchemy import VARIANT
from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

payload_type = JSON().with_variant(VARIANT, "snowflake")
eastern_time_zone = ZoneInfo("America/New_York")


def eastern_now() -> datetime:
    return datetime.now(eastern_time_zone)


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
        DateTime(timezone=True),
        nullable=False,
        default=eastern_now,
        server_default=text(
            "CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP())"
        ),
    )

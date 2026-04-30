from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .review_scrape_orm import Base

EST_TIMESTAMP_NTZ_SQL = (
    "CAST(CONVERT_TIMEZONE('America/New_York', CURRENT_TIMESTAMP()) AS TIMESTAMP_NTZ)"
)


class SitemapCrawlRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class SitemapCrawlRecordType(StrEnum):
    SITEMAP_DOCUMENT = "sitemap_document"
    DISCOVERED_URL = "discovered_url"


class SitemapCrawlUrlType(StrEnum):
    PDP = "pdp"
    CATEGORY = "category"
    UNKNOWN = "unknown"


class SitemapCrawlRecordStatus(StrEnum):
    PROCESSED = "processed"
    SKIPPED = "skipped"
    DISCOVERED = "discovered"
    ERROR = "error"


class SitemapCrawlSkipReason(StrEnum):
    PATTERN_MISMATCH = "pattern_mismatch"
    HOST_MISMATCH = "host_mismatch"
    DEPTH_LIMIT = "depth_limit"
    MAX_SITEMAPS_LIMIT = "max_sitemaps_limit"
    ALREADY_SEEN = "already_seen"
    NON_TARGET_URL_TYPE = "non_target_url_type"


class SitemapCrawlRunRecord(Base):
    __tablename__ = "sitemap_crawl_runs"

    crawl_run_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique identifier for one sitemap crawl execution.",
    )
    retailer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Retailer/profile key used for the crawl, for example `ikea`.",
    )
    entrypoint_url: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Seed sitemap document URL used to begin traversal.",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SitemapCrawlRunStatus.RUNNING.value,
        comment=("Expected values: running, completed, completed_with_errors, failed."),
    )
    processed_sitemaps_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of sitemap document URLs fetched and parsed in the run.",
    )
    skipped_sitemaps_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of encountered sitemap document URLs skipped by filters.",
    )
    discovered_url_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of accepted discovered leaf URLs emitted by the run.",
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of crawl-level or node-level errors observed in the run.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(EST_TIMESTAMP_NTZ_SQL),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="Set when the crawl run reaches a terminal status.",
    )


class SitemapCrawlRecord(Base):
    __tablename__ = "sitemap_crawl_records"

    retailer_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Retailer/profile key that owns this record.",
    )
    record_url: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        comment="Unique URL observed in sitemap traversal state for a retailer.",
    )
    parent_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Most recently observed parent sitemap URL for this record.",
    )
    record_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Expected values: sitemap_document, discovered_url.",
    )
    url_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Expected values for discovered URLs: pdp, category, unknown.",
    )
    depth: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Most recently observed traversal depth for this record.",
    )
    first_encountered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(EST_TIMESTAMP_NTZ_SQL),
    )
    latest_encountered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text(EST_TIMESTAMP_NTZ_SQL),
    )
    times_seen: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of crawl runs in which this URL has been encountered.",
    )
    first_crawl_run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="Crawl run that first discovered this record URL.",
    )
    last_crawl_run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="Most recent crawl run that encountered this record URL.",
    )
    record_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Expected values: processed, skipped, discovered, error.",
    )
    skip_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "Expected values when record_status=skipped: pattern_mismatch, "
            "host_mismatch, depth_limit, max_sitemaps_limit, already_seen, "
            "non_target_url_type."
        ),
    )
    child_sitemap_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Most recent count of child sitemap document URLs referenced by this "
            "sitemap document."
        ),
    )
    child_url_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Most recent count of child leaf URLs referenced by this sitemap document."
        ),
    )
    last_error_message: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Most recent error message associated with this record.",
    )

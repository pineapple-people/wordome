from dataclasses import dataclass, field
from enum import StrEnum


class ReviewSource(StrEnum):
    DOM = "dom"
    API = "api"


@dataclass(frozen=True)
class Review:
    author: str | None = None
    title: str | None = None
    body: str = ""
    rating: float | None = None
    rating_scale_max: int | None = 5
    date: str | None = None
    source: ReviewSource | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ReviewScrapeDomainMetadata:
    review_tabs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewScrapeMetadata:
    domain_metadata: ReviewScrapeDomainMetadata = field(
        default_factory=ReviewScrapeDomainMetadata
    )


@dataclass(frozen=True)
class ReviewScrapeResult:
    product_url: str
    review_page_url: str | None
    reviews_count: int | None = None
    reviews: list[Review] = field(default_factory=list)
    metadata: ReviewScrapeMetadata = field(default_factory=ReviewScrapeMetadata)

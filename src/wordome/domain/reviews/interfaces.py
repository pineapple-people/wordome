from typing import Protocol

from .models import ReviewScrapeResult


class ReviewsScraper(Protocol):
    async def scrape(self, product_url: str) -> ReviewScrapeResult: ...


class ReviewsRepository(Protocol):
    async def ensure_schema(self) -> None: ...

    async def append_scrape_snapshot(self, result: ReviewScrapeResult) -> str: ...

    async def get_latest_snapshot(
        self, product_url: str
    ) -> ReviewScrapeResult | None: ...

    async def list_snapshots(
        self, product_url: str, limit: int = 10
    ) -> list[ReviewScrapeResult]: ...

from typing import Protocol

from .models import ReviewScrapeResult


class ReviewsScraper(Protocol):
    async def scrape(self, product_url: str) -> ReviewScrapeResult: ...

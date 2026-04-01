import asyncio
from typing import List, Optional
from wordome.infrastructure import WebFetcher


class WebFetcherManager:
    """
    Manages fetching URLs using WebFetcher.
    Returns HTML strings ready for parsing.

    Note: can be used asynchronously or synchronously
    """

    def __init__(self, fetcher: WebFetcher = None):
        self.fetcher = fetcher or WebFetcher()

    # ---------------------------
    # Internal async helpers
    # ---------------------------
    async def _fetch_all_async(self, urls: List[str]) -> List[Optional[str]]:
        tasks = [self.fetcher.fetch(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _fetch_async(self, url: str) -> Optional[str]:
        return await self.fetcher.fetch(url)

    # ---------------------------
    # Public async API
    # ---------------------------
    async def fetch_all_async(self, urls: List[str]) -> List[Optional[str]]:
        """
        Fetch multiple URLs asynchronously
        """
        return await self._fetch_all_async(urls)

    async def fetch_async(self, url: str) -> Optional[str]:
        """
        Fetch a single URL asynchronously
        """
        return await self._fetch_async(url)

    # ---------------------------
    # Public synchronous API
    # ---------------------------
    def fetch_all(self, urls: List[str]) -> List[Optional[str]]:
        """
        Fetch multiple URLs synchronously
        """
        return asyncio.run(self._fetch_all_async(urls))

    def fetch(self, url: str) -> Optional[str]:
        """
        Fetch a single URL synchronously
        """
        return asyncio.run(self._fetch_async(url))
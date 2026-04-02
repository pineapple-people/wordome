import asyncio

from wordome.infrastructure import WebFetcher


class WebFetcherManager:
    """
    Manages fetching URLs using WebFetcher.
    Returns HTML strings ready for parsing.

    Note: supports both synchronous and asynchronous modes (blocking vs concurrency)
    """

    def __init__(self, fetcher: WebFetcher = None):
        self.fetcher = fetcher or WebFetcher()

    # ---------------------------
    # Internal async helpers
    # ---------------------------
    async def _fetch_all_async(self, urls: list[str]) -> list[str | None]:
        tasks = [self.fetcher.fetch(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _fetch_async(self, url: str) -> str | None:
        return await self.fetcher.fetch(url)

    async def _fetch_header_test_async(self) -> None:
        return await self.fetcher._fetch_header_test()

    # ---------------------------
    # Public async API
    # ---------------------------
    async def fetch_all_async(self, urls: list[str]) -> list[str | None]:
        """
        Fetch multiple URLs asynchronously
        """
        return await self._fetch_all_async(urls)

    async def fetch_async(self, url: str) -> str | None:
        """
        Fetch a single URL asynchronously
        """
        return await self._fetch_async(url)

    # ---------------------------
    # Public sync API
    # ---------------------------
    def fetch_all(self, urls: list[str]) -> list[str | None]:
        """
        Fetch multiple URLs synchronously
        """
        return asyncio.run(self._fetch_all_async(urls))

    def fetch(self, url: str) -> str | None:
        """
        Fetch a single URL synchronously
        """
        return asyncio.run(self._fetch_async(url))

    def fetch_header_test(self) -> None:
        """
        Fetch a single URL synchronously
        """
        return asyncio.run(self._fetch_header_test_async())

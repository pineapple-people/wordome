import asyncio
import json
from contextlib import asynccontextmanager

from curl_cffi.requests import AsyncSession


class WebFetcher:
    """
    Simple web fetcher for HTML content.

    Usage:
        fetcher = WebFetcher()
        html = await fetcher.fetch("https://example.com")
        results = await fetcher.fetch_many(["url1", "url2"])
    """

    DEFAULT_TIMEOUT = 15.0

    @asynccontextmanager
    async def _session(self, debug: bool = False):
        """Internal session manager"""
        async with AsyncSession(
            timeout=self.DEFAULT_TIMEOUT,
            debug=debug,
        ) as session:
            yield session

    async def fetch(self, url: str, debug: bool = False) -> str | None:
        """
        Fetch HTML content from a single URL
        """
        async with self._session(debug) as session:
            return await self._request(session, url)

    async def fetch_many(
        self, urls: list[str], debug: bool = False
    ) -> list[str | None]:
        """
        Fetch HTML content from multiple URLs concurrently
        """
        async with self._session(debug) as session:
            tasks = [self._request(session, url) for url in urls]
            return await asyncio.gather(*tasks)

    async def _request(self, session: AsyncSession, url: str) -> str | None:
        """
        Core request logic
        """
        try:
            response = await session.get(url=url, impersonate="chrome120")
            print(f"RESPONSE (HTTP status): {response.status_code}")
            return response.text
        except TimeoutError:
            print(f"Timeout (over {self.DEFAULT_TIMEOUT}s): {url}")
            return None
        except Exception as e:
            print(f"Error: {url} | ({e})")
            return None

    async def fetch_headers(
        self, url: str = "https://httpbin.org/headers", debug: bool = False
    ) -> dict | None:
        """
        Internal test function to observe request headers (generated in curl_cffi)
        """
        async with self._session(debug) as session:
            try:
                response = await session.get(url)
                headers_data = response.json()
                print(f"HEADERS from {url}:\n{json.dumps(headers_data, indent=2)}")
                return headers_data
            except Exception as e:
                print(f"Error (header debugger): {e}")
                return None

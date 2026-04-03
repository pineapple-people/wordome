import json

from curl_cffi.requests import AsyncSession


class WebFetcher:
    """
    Service class to provide HTML fetching functionality
    TODO: introduce "asynccontextmanager" to manage async session
    import contextlib import asynccontextmanager
    """

    DEFAULT_TIMEOUT = 15.0

    async def fetch(self, url: str, debug: bool = False) -> str | None:
        """
        Fetch HTML content from a given URL
        """
        async with AsyncSession(
            timeout=WebFetcher.DEFAULT_TIMEOUT,
            debug=debug,
        ) as session:
            try:
                response = await session.get(url=url, impersonate="chrome120")
                print(f"RESPONSE (HTTP status): {response.status_code}")
                return response.text
            except TimeoutError:
                print(f"Timeout (over {WebFetcher.DEFAULT_TIMEOUT}s): {url}")
            except Exception as e:
                print(f"Error: {url} | ({e})")
                return None

    async def _fetch_header_test(self) -> dict[any] | None:
        """
        Test function to observe request headers (managed by curl_cffi)
        """
        async with AsyncSession() as session:
            try:
                url = "https://httpbin.org/headers"
                response = await session.get(url)
                headers = json.dumps(response.json(), indent=2)
                print(f"HEADERS:\n{headers}")
                return headers
            except Exception as e:
                print(f"Error (header debugger): {e}")
                return None

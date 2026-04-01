from typing import Dict

import aiohttp


class WebFetcher:
    """
    Service class to provide HTML fetching functionality
    """

    DEFAULT_TIMEOUT = 15.0
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,lt;q=0.8,et;q=0.7,de;q=0.6",
    }
    DEFAULT_IGNORE_WORDS = ["and", "the"]

    @staticmethod
    async def log_request(method: str, url: str, headers: Dict):
        print(f"REQUEST[{method}]: {url}")
        print("HEADERS:")
        for k, v in headers.items():
            print(f"\t{k}: {v}")

    async def fetch(self, url: str) -> str | None:
        """
        Fetch HTML content from a given URL
        """
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT),
            headers=self.DEFAULT_HEADERS
        ) as session:
            try:
                await self.log_request("GET", url, self.DEFAULT_HEADERS)
                async with session.get(url) as response:
                    # Raise exception for 4xx or 5xx responses
                    response.raise_for_status()
                    print(f"RESPONSE STATUS: {response.status}")
                    return await response.text()
            except aiohttp.ClientResponseError as e:
                print(f"Server error with requesting {url} ({e.status})")
            except aiohttp.ClientError as e:
                print(f"General error with requesting {url}: {e}")
            return None

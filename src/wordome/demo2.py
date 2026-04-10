import asyncio
from importlib import resources

import wordome.resources as urls_source
from wordome.domain import BaseScraper
from wordome.infrastructure import WebFetcher


async def run_demo_async():
    """
    Script-like flow to showcase basic functionality
    - Fetching HTML from URLs
    - Example processing task to execute on the HTML content
    """

    fetcher = WebFetcher()
    scraper = BaseScraper()

    # URLs (temporarily sourced from local file)
    resource_path = resources.files(urls_source).joinpath("urls.txt")
    urls = resource_path.read_text(encoding="utf-8").splitlines()
    print(f"URLS: {urls}")

    # Trigger GET requests; fetches raw HTML content (per url)
    html_results: list[str] = await fetcher.fetch_many(urls)
    content_map: dict[str, str] = dict(zip(urls, html_results, strict=True))

    # Run content through dummy process to demo processings (WordStatsExtractor)
    for url, html in content_map.items():
        word_stats = scraper.process_html_to_stats(html)
        print(f"URL: {url}")
        if not word_stats:
            print("\t[No content extracted or words found]")
            continue
        for item in word_stats[:10]:
            print(
                f"\tword={item.word:12} | count={item.count:3} | freq={item.frequency:.4f}"
            )


def run_demo():
    """
    Synchronous wrapper over the async demo script
    """
    asyncio.run(run_demo_async())


# prevents auto execution during import
if __name__ == "__main__":
    """
    Standalone execution
    Debugging purposes
    """
    run_demo()

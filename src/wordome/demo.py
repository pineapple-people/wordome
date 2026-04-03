from importlib import resources

import wordome.resources as urls_source
from wordome.domain import WordStats, WordStatsExtractor
from wordome.infrastructure import WebFetcherManager


def run_demo():
    # Component to fetch HTML content
    fetcher_manager = WebFetcherManager()

    # Component to operate/process the HTML content (business logic)
    extractor = WordStatsExtractor()

    # URLs (temporarily sourced from local file)
    resource_path = resources.files(urls_source).joinpath("urls.txt")
    urls = resource_path.read_text(encoding="utf-8").splitlines()
    print(f"URLS: {urls}")

    # Trigger GET requests; fetches raw HTML content (per url)
    html_results: list[str] = fetcher_manager.fetch_all(urls)
    content_map: dict[str, str] = dict(zip(urls, html_results, strict=True))

    # Run content through dummy process to demo processings (WordStatsExtractor)
    for url, html in content_map.items():
        word_stats: list[WordStats] = extractor.process(html)
        print(f"URL: {url}")
        for item in word_stats:
            print(f"\tword={item.word}, count={item.count}, freq={item.frequency}")


# prevents auto execution during import
if __name__ == "__main__":
    """
    Standalone execution for debugging purposes only
    """
    run_demo()

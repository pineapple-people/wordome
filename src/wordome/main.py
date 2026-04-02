from typing import Dict, List

from wordome.infrastructure import WebFetcherManager
from wordome.domain import WordStatsExtractor, WordStats

from importlib import resources
import wordome.resources as urls_source

# A script to verify basic functionality

# Component to fetch HTML content
fetcher_manager = WebFetcherManager()

# Component to operate/process the HTML content (business logic)
extractor = WordStatsExtractor()

# URLs (temporarily sourced from local file)
resource_path = resources.files(urls_source).joinpath("urls.txt")
urls = resource_path.read_text(encoding="utf-8").splitlines()
print(f"URLS: {urls}")

# Trigger GET requests; fetches raw HTML content (per url)
html_results: List[str] = fetcher_manager.fetch_all(urls)
content_map: Dict[str, str] = {url: html for url, html in zip(urls, html_results)}

# Run content through dummy process to demo processings (WordStatsExtractor)
for url, html in content_map.items():
    word_stats: List[WordStats] = extractor.process(html)
    print(f"URL: {url}")
    for item in word_stats:
        print(f"\tword={item.word}, count={item.count}, freq={item.frequency}")
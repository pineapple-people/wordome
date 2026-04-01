from typing import List

from wordome.infrastructure import WebFetcherManager
from wordome.domain import WordStatsExtractor, WordStats

# A simple script to verify
# url = "https://www.google.com"

# url = "http://www.wayfair.com"
# url = "https://www.wayfair.com/kitchen-tabletop/pdp/vitamix-stainless-steel-container-vtm10031.html"

url = "http://www.amazon.com/Fendi-Pre-loved-Patent-Leather-Baguette/dp/B0GT6VHKBS/"
# url = "http://en.wikipedia.org/wiki/Web_scraping"
# url = 'http://www.homedepot.com/p/6ft-x-8ft-Pine-Pressure-Treated-Privacy-Dog-Ear-Flat-Wood-Fence-Panel-158083/203733689'


# initalize relevant components 
fetcher_manager = WebFetcherManager()
extractor = WordStatsExtractor()

# invoke get request; should retreive the raw HTML (from GET response)
html_raw = fetcher_manager.fetch(url)

if html_raw:
    print(f"CONTENT (len): {len(html_raw)}")
    word_stats: List[WordStats] = extractor.process(html_raw)
    for item in word_stats:
        print(f"\tword={item.word}, count={item.count}, freq={item.frequency}")
    

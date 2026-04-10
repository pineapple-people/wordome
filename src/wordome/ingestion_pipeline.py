import asyncio
import json
from importlib import resources

import wordome.resources as urls_source
from wordome.domain.component.site_parser import SiteParser
from wordome.infrastructure import DBManager
from wordome.infrastructure import WebFetcher


async def run_pipeline_async():
    '''ecouple product information and reviews into a relational database schema'''
    # 1. Initialization
    db = DBManager("wordome_v1.db")
    fetcher = WebFetcher()
    total_reviews_saved = 0
    total_products_saved = 0

    # Load data
    resource_path = resources.files(urls_source).joinpath("urls.txt")
    urls = [line.strip() for line in resource_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    if not urls:
        print("No URLs to process. Exiting.")
        return

    print(f"Starting pipeline for {len(urls)} URLs...")

    # Load configuration
    with open("config/sites_config.json") as f:
        config_data = json.load(f)
    parser = SiteParser(config_data)

    # 2. Batch fetch
    html_results = await fetcher.fetch_many(urls)
    content_map = dict(zip(urls, html_results))
    
    # 3. Iteration logic
    for url, html in content_map.items():
        if not html:
            print(f"[FAILED] Could not fetch content for: {url}")
            continue

        # A. Identify type (Dispatcher)
        site_key = None
        for key in config_data.keys():
            if key in url.lower():
                site_key = key
                break

        if not site_key:
            print(f"[SKIP] No config found for: {url}")
            continue

        print(f" [MATCH] Processing [{site_key}] | URL: {url}")

        try:
            # B. Parse and store product metadata (Parent)
            product_info = parser.parse_product_info(html, site_key, url=url)
            
            if product_info:
                db.save_product(product_info)
                print(f"[PRODUCT] Saved: {product_info.product_name} ({product_info.product_id})")
                total_products_saved += 1
                
                # C. Parse and store reviews (Children)
                # Only save reviews after product is successfully saved
                structured_reviews = parser.parse_reviews(html, site_key)

                if structured_reviews:
                    for r in structured_reviews:
                        r.product_id = product_info.product_id
                    
                    db.save_review_batch(structured_reviews)
                    print(f"[REVIEWS] Stored {len(structured_reviews)} reviews.")
                    total_reviews_saved += len(structured_reviews)
                else:
                    print(f"[WARN] No reviews found on this page.")
            else:
                print(f"[ERROR] Could not parse product info from {url}. Skipping reviews.")

        except Exception as e:
            print(f"[CRITICAL] Failed to process {url}: {e}")

    print("\n" + "="*30)
    print("--- Pipeline Finished ---")
    print(f"Total Products saved/updated: {total_products_saved}")
    print(f"Total Reviews saved: {total_reviews_saved}")
    print("="*30)

def start_ingestion():
    """
    Synchronous wrapper over the async demo script
    """
    asyncio.run(run_pipeline_async())

# prevents auto execution during import
if __name__ == "__main__":
    """
    Standalone execution
    Debugging purposes
    """
    start_ingestion()

if __name__ == "__main__":
    start_ingestion()
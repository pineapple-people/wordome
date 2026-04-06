import asyncio
import json
from pathlib import Path
from wordome.infrastructure import WebFetcher
from wordome.infrastructure import DBManager
from wordome.domain import SiteParser


import asyncio
from importlib import resources

import wordome.resources as urls_source
from wordome.infrastructure import WebFetcher


async def run_pipeline_async():
    # --- 1. 初始化 ---
    db = DBManager("wordome_v1.db")
    fetcher = WebFetcher()
    total_saved = 0

    # URLs (temporarily sourced from local file)
    resource_path = resources.files(urls_source).joinpath("urls.txt")
    urls = resource_path.read_text(encoding="utf-8").splitlines()
    print(f"URLS: {urls}")

    # Trigger GET requests; fetches raw HTML content (per url)
    html_results: list[str] = await fetcher.fetch_many(urls)
    content_map: dict[str, str] = dict(zip(urls, html_results, strict=True))
    
    with open("config/sites_config.json", "r") as f:
        config_data = json.load(f)
    parser = SiteParser(config_data)


    if not urls:
        print("No URLs to process. Exiting.")
        return


    # --- 3. 异步抓取 ---
    html_results = await fetcher.fetch_many(urls)
    content_map = dict(zip(urls, html_results))

    # --- 4. 循环处理逻辑 (保持不变) ---
    for url, html in content_map.items():
        # ... 这里是你之前的 dispatcher 和 parser 逻辑 ...
        # 如果域名没在 sites_config.json 里，这里会自动 skip
        pass 

        # A. 识别身份 (Dispatcher 逻辑)
        # 遍历配置里的 key，比如 "amazon", "yelp"
        site_key = None
        for key in config_data.keys():
            if key in url.lower():
                site_key = key
                break
        
        # B. 如果匹配成功就处理，不匹配就跳过
        if not site_key:
            print(f"⏩ [SKIP] No config found for: {url}")
            continue

        print(f"🎯 [MATCH] Found config for [{site_key}]. Parsing...")

        try:
            structured_reviews = parser.parse(html, site_key)
            
            if structured_reviews:
                # D. 存入数据库
                db.save_batch(structured_reviews)
                print(f"✅ [SAVE] Successfully stored {len(structured_reviews)} reviews.")
                total_saved += len(structured_reviews)
            else:
                print(f"⚠️ [WARN] No reviews extracted from {url} despite matching config.")
                
        except Exception as e:
            print(f"❌ [ERROR] Failed to process {url}: {e}")

    print(f"\n--- Pipeline Finished ---")
    print(f"Total reviews saved to database: {total_saved}")

def main():
    try:
        asyncio.run(run_pipeline_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
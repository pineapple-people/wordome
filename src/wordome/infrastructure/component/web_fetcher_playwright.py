import asyncio
from playwright.async_api import async_playwright
import random
import os

# --- 单页抓取函数 ---
async def fetch_html_emergency(url: str):
    async with async_playwright() as p:
        # 1. 极简启动
        browser = await p.chromium.launch(headless=False, args=["--disable-http2"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 2. 彻底禁用不需要的资源
        await page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,gif}", lambda route: route.abort())

        try:
            print(f"🎯 正在执行快闪抓取: {url}")
            await page.goto(url, wait_until="commit", timeout=30000)
            
            # 仅仅等待 3 秒给内容“呼吸”时间
            await asyncio.sleep(3) 

            # 强行扣取 DOM
            html_content = await page.evaluate("document.documentElement.outerHTML")
            return html_content

        except Exception as e:
            print(f"❌ 抢收失败: {str(e)}")
            return None
        finally:
            await browser.close()

# --- 批量翻页逻辑 ---
async def batch_crawl(sku_id, total_pages=5):
    if not os.path.exists("bestbuy_pages"):
        os.makedirs("bestbuy_pages")
        
    all_results = []
    
    for page_num in range(1, total_pages + 1):
        print(f"\n📦 [进度 {page_num}/{total_pages}]")
        
        # 构造带有 page 参数的 URL
        # 注意：Best Buy 的独立评论页路径通常是 /site/reviews/product-name/SKU
        url = f"https://www.bestbuy.com/site/reviews/x/{sku_id}?page={page_num}"
        
        html = await fetch_html_emergency(url)
        
        if html and len(html) > 10000: # 简单校验，防止抓到空白页
            file_path = f"bestbuy_pages/page_{page_num}.html"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ 第 {page_num} 页已保存至 {file_path}")
            all_results.append(html)
        else:
            print(f"🛑 第 {page_num} 页内容异常或抓取失败，停止后续采集。")
            break
            
        # 模拟人类翻页间隙，保护 Pineapplecat 的 IP
        wait_time = random.uniform(5, 10)
        print(f"💤 休息 {wait_time:.1f} 秒...")
        await asyncio.sleep(wait_time)
        
    return all_results

# --- Main 入口 ---
async def main():
    print("🚀 Wordome Best Buy Ingestion Pipeline Started")
    
    # 填入那款 Beats 耳机的 SKU
    target_sku = "6501017" 
    
    pages_data = await batch_crawl(target_sku, total_pages=3)
    
    print(f"\n✨ 采集任务结束！共计成功获取 {len(pages_data)} 页数据。")
    print("📂 请在 bestbuy_pages 文件夹中查看结果。")

if __name__ == "__main__":
    # 启动异步事件循环
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 用户手动停止抓取")
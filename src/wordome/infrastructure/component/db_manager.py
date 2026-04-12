import asyncio
from playwright.async_api import async_playwright

async def fetch_html(url: str):
    async with async_playwright() as p:
        # 1. 启动浏览器，保留你发现的解药 --disable-http2
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-http2"] 
        )
        
        # 2. 模拟一个真实且干净的浏览器环境
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        
        try:
            print(f"🌐 正在获取 HTML: {url}")
            
            # 3. 核心改进：不要用 networkidle
            # 使用 'domcontentloaded' 意味着 HTML 结构加载完即停止等待
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 4. 强制等待几秒，确保那些异步加载的评论（React/Vue 渲染）能跑出来
            await page.wait_for_timeout(5000) 
            
            # 5. 拿到渲染后的完整 HTML
            html_content = await page.content()
            print(f"✅ 成功获取 HTML，大小: {len(html_content)} 字节")
            
            return html_content

        except Exception as e:
            print(f"❌ 获取失败: {e}")
            return None
        finally:
            await browser.close()

async def main():
    target_url = "https://www.bestbuy.com/site/reviews/beats-studio-pro-wireless-noise-cancelling-over-the-ear-headphones-black/6501017"
    html = await fetch_html(target_url)
    
    if html:
        with open("raw_content.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("💾 文件已保存至 raw_content.html")

if __name__ == "__main__":
    asyncio.run(main())
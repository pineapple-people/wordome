import asyncio
import random
import os
from playwright.async_api import async_playwright
import playwright_stealth

# --- 核心配置区 ---
TARGET_SKU = "6501017"
PRODUCT_SLUG = "beats-studio-pro-wireless-noise-cancelling-over-the-ear-headphones-black"
BSIN = "JJ8ZHR9K2T"
TOTAL_PAGES = 3  # 你想抓取的页数
OUTPUT_DIR = "bestbuy_pages"

async def fetch_page_with_stealth(url, page_num):
    """
    单页抓取核心函数：集成了隐身指纹与快速抢收策略
    """
    async with async_playwright() as p:
        print(f"🔧 启动隐身浏览器 - 第 {page_num} 页...")
        
        # 1. 基础启动参数：禁用 HTTP/2 是 Best Buy 的关键解药
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-http2",
                "--disable-blink-features=AutomationControlled", # 抹掉自动化特征
                "--no-sandbox"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            extra_http_headers={"Referer": "https://www.bestbuy.com/"}
        )
        
        page = await context.new_page()

        # 2. 注入隐身指纹 (适配 2.0.3 版本)
        try:
            if hasattr(playwright_stealth, 'stealth_async'):
                await playwright_stealth.stealth_async(page)
            else:
                await playwright_stealth.stealth(page)
        except Exception as e:
            print(f"⚠️ Stealth 插件注入提醒: {e}")

        # 3. 资源拦截：屏蔽图片、字体和 CSS 极大提高成功率并避开 Akamai 陷阱
        await page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,gif}", lambda route: route.abort())

        try:
            print(f"📡 尝试连接: {url}")
            # wait_until="commit"：只要服务器开始传数据我们就接手，不给反爬脚本完整执行的机会
            await page.goto(url, wait_until="commit", timeout=45000)
            
            print("🚀 连接成功，隐身渲染中 (8s)...")
            await asyncio.sleep(8) 

            print("📸 正在强行提取 DOM 数据...")
            # 使用 evaluate 直接从内存读取 HTML，绕过 content() 可能触发的完整性检查
            html_content = await asyncio.wait_for(
                page.evaluate("document.documentElement.outerHTML"), 
                timeout=15.0
            )
            
            return html_content

        except asyncio.TimeoutError:
            print(f"❌ 第 {page_num} 页读取超时，Akamai 防御过强。")
            return None
        except Exception as e:
            print(f"❌ 运行异常: {str(e)[:100]}")
            return None
        finally:
            await browser.close()

async def batch_crawl():
    """
    翻页逻辑与文件持久化
    """
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"🔥 开始执行 Wordome 采集任务 | SKU: {TARGET_SKU}")
    
    success_count = 0
    
    for page_num in range(1, TOTAL_PAGES + 1):
        # 构造“长格式”URL，这是目前最稳健的路径
        url = f"https://www.bestbuy.com/product/{PRODUCT_SLUG}/{BSIN}/sku/{TARGET_SKU}/reviews?page={page_num}&pageSize=20"
        
        print(f"\n--- [进度: {page_num}/{TOTAL_PAGES}] ---")
        html = await fetch_page_with_stealth(url, page_num)
        
        if html and len(html) > 30000: # 正常页面通常在 100KB 以上
            file_path = os.path.join(OUTPUT_DIR, f"page_{page_num}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ 抓取成功！已保存至: {file_path} ({len(html)} 字节)")
            success_count += 1
        else:
            print(f"🛑 第 {page_num} 页未能获取有效数据。")
            # 如果第一页就失败，通常是 IP 被封，建议停止任务
            if page_num == 1:
                print("🚨 检测到首屏即遭拦截，请尝试更换 IP 或休息一会儿。")
                break
            
        # 模拟人类阅读时间，避免触发频率限制
        sleep_time = random.uniform(10, 20)
        print(f"💤 冷却中 ({sleep_time:.1f}s)...")
        await asyncio.sleep(sleep_time)

    print(f"\n✨ 任务结束！成功采集 {success_count}/{TOTAL_PAGES} 页内容。")

if __name__ == "__main__":
    try:
        asyncio.run(batch_crawl())
    except KeyboardInterrupt:
        print("\n👋 任务被用户中断。")
import asyncio
from wordome.infrastructure import WebFetcher  

async def main():
    fetcher = WebFetcher()
    url = "https://www.bestbuy.com/product/beats-studio-pro-wireless-noise-cancelling-over-the-ear-headphones-black/JJ8ZHR9K2T/sku/6501017/reviews?pageSize=20"
    html = await fetcher.fetch(url)   # 默认超时 15 秒
    if html:
        print(f"成功获取 HTML，长度 {len(html)} 字符")
        # 可以保存到文件或用 BeautifulSoup 解析
        with open("output.html", "w", encoding="utf-8") as f:
            f.write(html)
    else:
        print("获取失败")

if __name__ == "__main__":
    asyncio.run(main())
import re
from datetime import datetime
from bs4 import BeautifulSoup
import dateparser
from ..model.review import ScrapedReview

class SiteParser:
    def __init__(self, config: dict):
        self.config = config

    def clean_rating(self, raw_rating: str) -> float:
        if not raw_rating: return 0.0
        match = re.search(r"(\d+(\.\d+)?)", raw_rating)
        return float(match.group(1)) if match else 0.0

    def clean_date(self, raw_date: str) -> datetime:
        if not raw_date: return datetime.now()
        dt = dateparser.parse(raw_date)
        return dt if dt else datetime.now()
    
    # src/wordome/domain/component/site_parser.py

    def parse(self, html: str, site_key: str) -> list[ScrapedReview]:
        if site_key not in self.config:
            return []

        cfg = self.config[site_key]
        soup = BeautifulSoup(html, "html.parser")
        
        containers = soup.select(cfg["container"])
        reviews = []

        for item in containers:
            try:
                raw_data = {}
                for field, rule in cfg["selectors"].items():
                    # --- 核心修复逻辑 ---
                    css_selector = rule.get("css")
                    
                    if css_selector:
                        # 如果有 css 路径，就往里找子元素
                        target_element = item.select_one(css_selector)
                    else:
                        # 如果没有 css 路径，说明数据就在 container（盒子）自己身上
                        target_element = item

                    if target_element:
                        if rule.get("type") == "text":
                            raw_data[field] = target_element.get_text(strip=True)
                        elif "attr" in rule:
                            raw_data[field] = target_element.get(rule["attr"])
                    else:
                        raw_data[field] = None
                # ------------------

                review_obj = ScrapedReview(
                    source=site_key,
                    product_id="B09YL81PWH", # 以后可以从 URL 提取
                    review_id=raw_data.get("review_id") or "unknown",
                    rating=self.clean_rating(raw_data.get("rating")),
                    title=raw_data.get("title") or "",
                    content=raw_data.get("content") or "",
                    review_date=self.clean_date(raw_data.get("review_date")),
                    is_verified=bool(raw_data.get("is_verified"))
                )
                print(f"REVIEW_OBJ: {review_obj}")
                reviews.append(review_obj)
            except Exception as e:
                print(f"Error parsing individual review: {e}")
                
        return reviews
    
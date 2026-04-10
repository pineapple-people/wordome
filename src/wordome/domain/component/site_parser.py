import re
from datetime import datetime
from typing import Optional, List, Tuple
import dateparser
from bs4 import BeautifulSoup
from ..model.data_model import ScrapedProductInfo, ScrapedReview

class SiteParser:
    def __init__(self, config: dict):
        self.config = config

    # tools
    def clean_rating(self, raw_rating: str) -> float:
        """Get float number ratings from str"""
        if not raw_rating:
            return 0.0
        match = re.search(r"(\d+(\.\d+)?)", raw_rating)
        return float(match.group(1)) if match else 0.0

    def clean_date(self, raw_date: str) -> datetime:
        """Get datetime"""
        if not raw_date:
            return datetime.now()
        dt = dateparser.parse(raw_date)
        return dt if dt else datetime.now()

    def _clean_categories(self, raw_rank_text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse Amazon ranking string, convert it to main category and sub category

        eg.

        Input:
        #364 in Health & Household (See Top 100...)#9 inBox Tissues

        Output:
        ("Health & Household", "Box Tissues")
        """
        if not raw_rank_text:
            return None, None

    
        # #\d+(?:,\d+)? -> matches ranking numbers like #364 or #14,000
        # \s*in\s* -> matches ' in ', allowing flexible spacing (fixes cases like 'inBox')
        # ([^(\n\r#]+) -> captures category text until encountering '(', '#', or newline
        pattern = r"#\d+(?:,\d+)?\s*in\s*([^(\n\r#]+)"
        
        matches = re.findall(pattern, raw_rank_text)
        
        # clear the blankspace in the end
        main_cat = matches[0].strip() if len(matches) > 0 else None
        sub_cat = matches[1].strip() if len(matches) > 1 else None
        
        return main_cat, sub_cat

    def _get_asin_from_url(self, url: str) -> Optional[str]:
        """Extract 10-character ASIN directly from URL using regex"""
        match = re.search(r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})", url)
        return match.group(1) if match else None
    
    def clean_price(self, raw_price: str) -> float:
        """
        Input: "$19.20" or "19.20"
        Output: 19.2
        """
        if not raw_price:
            return 0.0
        # remove units and signs
        clean_str = re.sub(r'[^\d.]', '', raw_price)
        try:
            return float(clean_str)
        except ValueError:
            return 0.0
    
    # Product table
    def parse_product_info(self, html: str, site_key: str, url: str = "") -> Optional[ScrapedProductInfo]:
        site_cfg = self.config.get(site_key, {}) # match CSS selector to site_key
        cfg = site_cfg.get("product_meta")
        if not cfg: return None
        
        soup = BeautifulSoup(html, "html.parser")
        container = soup.find("body") or soup

        raw_data = {}
        for field, rule in cfg.get("selectors", {}).items():
            css = rule.get("css", "").replace(":contains", ":-soup-contains")
            element = container.select_one(css)
            
            if element:
                if "attr" in rule:
                    raw_data[field] = element.get(rule["attr"])
                else:
                    raw_data[field] = element.get_text(strip=True)
            else:
                raw_data[field] = None
        
        p_id = self._get_asin_from_url(url)
    
        # try to get product_id from url, otherwise from page
        if not p_id:
            asin_input = soup.select_one('input#ASIN, input[name="ASIN"]')
            p_id = asin_input.get("value") if asin_input else "unknown"

        # convert rank to category
        rank_text = raw_data.get("category_raw") or raw_data.get("category")
        main_cat, sub_cat = self._clean_categories(rank_text)
        print(rank_text)

        return ScrapedProductInfo(
            source=site_key,
            product_id=p_id,
            product_name=raw_data.get("product_name") or "Unknown Product",
            brand=raw_data.get("brand"),
            manufacturer=raw_data.get("manufacturer"),
            main_category=main_cat, 
            sub_category=sub_cat,
            price = self.clean_price(raw_data.get("price")),
            average_rate=self.clean_rating(raw_data.get("average_rate")),
            total_ratings=int(re.sub(r'[^\d]', '', raw_data.get("total_ratings") or "0"))
        )

    # Review table
    def parse_reviews(self, html: str, site_key: str) -> List[ScrapedReview]:
        site_cfg = self.config.get(site_key, {})
        cfg = site_cfg.get("review_selectors")
        if not cfg:
            return []

        soup = BeautifulSoup(html, "html.parser")
        container_selector = cfg.get("container")
        if not container_selector:
            return []
            
        containers = soup.select(container_selector)
        reviews = []

        for item in containers:
            try:
                raw_data = {}
                for field, rule in cfg.get("selectors", {}).items():
                    css_selector = rule.get("css")

                    if css_selector:
                        # Child element
                        target_element = item.select_one(css_selector)
                    else:
                        # Data is at the current node
                        target_element = item

                    if target_element:
                        if rule.get("type") == "text":
                            raw_data[field] = target_element.get_text(strip=True)
                        elif "attr" in rule:
                            raw_data[field] = target_element.get(rule["attr"])
                    else:
                        raw_data[field] = None

                review_obj = ScrapedReview(
                    source=site_key,
                    product_id=raw_data.get("product_id") or "unknown",
                    review_id=raw_data.get("review_id") or "unknown",
                    rating=self.clean_rating(raw_data.get("rating")),
                    title=raw_data.get("title") or "",
                    content=raw_data.get("content") or "",
                    review_date=self.clean_date(raw_data.get("review_date")),
                    is_verified=bool(raw_data.get("is_verified")),
                )
                reviews.append(review_obj)
            except Exception as e:
                print(f"Error parsing individual review: {e}")

        return reviews
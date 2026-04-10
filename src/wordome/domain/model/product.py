from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScrapedProductInfo:
    source: str
    product_id: str  # ASIN (PK)
    product_name: str
    brand: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    price: float | None = None
    average_rate: float = 0.0
    total_ratings: int = 0
    updated_at: datetime = datetime.now()  # record scraping time

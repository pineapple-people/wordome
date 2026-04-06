from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ScrapedProductInfo:
    source: str           
    product_id: str        # ASIN (PK)
    product_name: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    average_rate: float = 0.0
    total_ratings: int = 0
    updated_at: datetime = datetime.now() # 记录抓取时间
    


    
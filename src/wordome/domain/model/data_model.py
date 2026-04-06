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
    mian_category: Optional[str] = None
    sub_category: Optional[str] = None
    price: Optional[float] = None
    average_rate: float = 0.0
    total_ratings: int = 0
    updated_at: datetime = datetime.now() # scraping time


@dataclass
class ScrapedReview:
    source: str           
    product_id: str       # FK
    review_id: str        # unique ID, PK
    rating: float         # rating (1.0 - 5.0)
    title: str            
    content: str          
    review_date: datetime 
    is_verified: bool     # verified purchase or not
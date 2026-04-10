from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ScrapedProductInfo:
    product_id: str        # ASIN (PK)
    source: str
    product_name: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    main_category: Optional[str] = None  
    sub_category: Optional[str] = None   
    price: float = 0.0
    average_rate: float = 0.0
    total_ratings: int = 0
    updated_at: datetime = datetime.now()

@dataclass
class ScrapedReview:
    review_id: str         # PK
    product_id: str        # FK
    source: str
    rating: float
    title: str
    content: str
    review_date: datetime
    is_verified: bool      # verify purchase or not
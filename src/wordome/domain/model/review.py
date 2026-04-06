from dataclasses import dataclass
from datetime import datetime
from typing import Optional

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


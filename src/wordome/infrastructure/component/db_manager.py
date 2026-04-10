import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import List
from wordome.domain.model.review import ScrapedReview
from wordome.domain.model.product import ScrapedProductInfo 

class DBManager:
    def __init__(self, db_path: str = "wordome.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database: create a product table and a review table"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. product table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,  -- ASIN
                    source TEXT,
                    product_name TEXT,
                    brand TEXT,
                    manufacturer TEXT,
                    main_category TEXT, 
                    sub_category TEXT, 
                    price REAL,
                    average_rate REAL,
                    total_ratings INTEGER,
                    updated_at TIMESTAMP
                )
            """)

            # 2. review table linked via product_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    source TEXT,
                    product_id TEXT,
                    rating REAL,
                    title TEXT,
                    content TEXT,
                    review_date TIMESTAMP,
                    is_verified INTEGER,
                    FOREIGN KEY (product_id) REFERENCES products (product_id)
                )
            """)
            conn.commit()

    def save_product(self, product: ScrapedProductInfo):
        """Save or update product information (UPSERT logic)"""
        data = asdict(product)

        # Ensure the timestamp is recorded
        data["updated_at"] = datetime.now().isoformat()

        # SQL statement corresponding to the new field names
        query = """
            INSERT OR REPLACE INTO products 
            (product_id, source, product_name, brand, manufacturer, 
             main_category, sub_category, price, average_rate, total_ratings, updated_at)
            VALUES 
            (:product_id, :source, :product_name, :brand, :manufacturer, 
             :main_category, :sub_category, :price, :average_rate, :total_ratings, :updated_at)
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query, data)
            conn.commit()

    def save_review(self, review: ScrapedReview):
        """Save single comment"""
        data = asdict(review)
        data["is_verified"] = 1 if data["is_verified"] else 0
        if isinstance(data["review_date"], datetime):
            data["review_date"] = data["review_date"].isoformat()

        query = """
            INSERT OR REPLACE INTO reviews 
            (review_id, source, product_id, rating, title, content, review_date, is_verified)
            VALUES (:review_id, :source, :product_id, :rating, :title, :content, :review_date, :is_verified)
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(query, data)
            conn.commit()

    def save_review_batch(self, reviews: List[ScrapedReview]):
        """Batch insert reviews"""
        if not reviews:
            return

        with sqlite3.connect(self.db_path) as conn:
            query = """
                INSERT OR REPLACE INTO reviews 
                (review_id, source, product_id, rating, title, content, review_date, is_verified)
                VALUES (:review_id, :source, :product_id, :rating, :title, :content, :review_date, :is_verified)
            """
            processed_data = []
            for r in reviews:
                d = asdict(r)
                d["is_verified"] = 1 if d["is_verified"] else 0
                if isinstance(d["review_date"], datetime):
                    d["review_date"] = d["review_date"].isoformat()
                processed_data.append(d)

            conn.executemany(query, processed_data)
            conn.commit()
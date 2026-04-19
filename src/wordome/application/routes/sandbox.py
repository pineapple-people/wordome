from fastapi import APIRouter
from pydantic import BaseModel

from wordome.domain import ReviewSectionDetector
from wordome.infrastructure import WebFetcher
from wordome.infrastructure.database.database_connection import DatabaseConnection

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher = WebFetcher()
review_detector = ReviewSectionDetector()


@router.get("/")
async def sandbox_root():
    """
    Sandbox
    """
    return {
        "name": "Sandbox",
        "description": "Debug and testing endpoints",
        "endpoints": ["/headers", "/fetch_html"],
    }


@router.get("/fetch/headers")
async def fetch_headers():
    """
    Show request headers (generated via curl_cffi)
    Note: unique variation generated per request
    """
    return await web_fetcher.fetch_headers()


class FetchRequest(BaseModel):
    url: str


@router.post("/fetch/html")
async def fetch_html(request: FetchRequest):
    """
    Get HTML for a given URL
    """
    return await web_fetcher.fetch(request.url)


@router.post("/detect/reviews")
async def detect_reviews(request: FetchRequest):
    """
    Detects whether HTML contains a review section
    """
    html = await web_fetcher.fetch(request.url)
    if html:
        return review_detector.process(html)


@router.get("/db/ping")
def db_ping():
    """Test Snowflake connectivity"""
    conn = None
    cur = None
    try:
        db_connection = DatabaseConnection()

        conn = db_connection.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_TIMESTAMP()")
        result = cur.fetchone()

        return {
            "status": "connected",
            "snowflake_time": str(result[0]),
            "database": conn.database,
            "schema": conn.schema,
        }
    except Exception as e:
        return {"status": "failed", "error": e}

    finally:
        if conn:
            conn.close()
        if cur:
            cur.close()

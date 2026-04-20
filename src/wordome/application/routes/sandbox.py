from fastapi import APIRouter, Depends
from pydantic import BaseModel

from wordome.domain import ReviewSectionDetector
from wordome.infrastructure import WebFetcher
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher = WebFetcher()
review_detector = ReviewSectionDetector()


def _get_repository() -> SnowflakeRepository:
    """
    Instantiate Snowflake Repository instance
    """
    return SnowflakeRepository()


@router.get("/")
async def sandbox_root():
    """
    Return a quick overview of the sandbox routes.
    """
    return {
        "name": "Sandbox",
        "description": "Debug and testing endpoints",
        "endpoints": ["/headers", "/fetch_html", "/db/ping"],
    }


@router.get("/fetch/headers")
async def fetch_headers():
    """
    Fetch and return the upstream request headers for debugging.
    """
    return await web_fetcher.fetch_headers()


class FetchRequest(BaseModel):
    url: str


@router.post("/fetch/html")
async def fetch_html(request: FetchRequest):
    """
    Fetch raw HTML for the requested URL.
    """
    return await web_fetcher.fetch(request.url)


@router.post("/detect/reviews")
async def detect_reviews(request: FetchRequest):
    """
    Fetch HTML and run the review detector against it.
    """
    html = await web_fetcher.fetch(request.url)
    if html:
        return review_detector.process(html)


@router.get("/db/ping")
async def db_ping(
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Verify the Snowflake connection can open and run a simple query.
    """
    try:
        await sf_repository.health_check()
        message = await sf_repository.ping()
        warehouse_count = await sf_repository.get_warehouse_count()

        return {
            "success": True,
            "message": message,
            "warehouse_count": warehouse_count,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

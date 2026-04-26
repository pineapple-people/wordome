from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from wordome.domain import ReviewsScraper
from wordome.domain.demo import ReviewSectionDetector
from wordome.infrastructure import ReviewsScraperIkea, WebFetcher
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher = WebFetcher()
review_detector = ReviewSectionDetector()


def _get_repository(request: Request) -> SnowflakeRepository:
    repository = getattr(request.app.state, "snowflake_repository", None)
    if not isinstance(repository, SnowflakeRepository):
        raise RuntimeError("Snowflake repository is not configured on app.state")
    return repository


@router.get("/")
async def sandbox_root():
    """
    Return a quick overview of the sandbox routes.
    """
    return {
        "name": "Sandbox",
        "description": "Debug and testing endpoints",
        "endpoints": [
            "/headers",
            "/fetch_html",
            "/reviews/ikea",
            "/db/ping",
            "/db/health",
            "/db/bootstrap",
            "/db/reviews/ikea",
            "/db/reviews/latest",
            "/db/reviews/recent",
        ],
    }


@router.get("/fetch/headers")
async def fetch_headers():
    """
    Fetch and return the upstream request headers for debugging.
    """
    return await web_fetcher.fetch_headers()


class FetchRequest(BaseModel):
    url: str


class RecentFetchRequest(FetchRequest):
    limit: int = 10


def _get_ikea_scraper(request: Request) -> ReviewsScraper:
    scraper = getattr(request.app.state, "ikea_scraper", None)
    if not isinstance(scraper, ReviewsScraperIkea):
        raise RuntimeError("IKEA scraper is not configured on app.state")
    return scraper


async def _scrape_ikea_reviews(
    url: str,
    ikea_scraper: ReviewsScraper,
):
    return await ikea_scraper.scrape(url)


async def _scrape_and_append_ikea_reviews(
    url: str,
    ikea_scraper: ReviewsScraper,
    sf_repository: SnowflakeRepository,
):
    result = await _scrape_ikea_reviews(url, ikea_scraper)
    snapshot_event_id = await sf_repository.append_scrape_snapshot(result)
    return result, snapshot_event_id


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
    Verify the Snowflake connection can establish a minimal DB session.
    """
    try:
        return {
            "success": await sf_repository.is_connected(),
            "message": None,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/db/health")
async def db_health(
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Return repository-level Snowflake diagnostics.
    """
    return await sf_repository.get_repository_health()


@router.post("/db/bootstrap")
async def db_bootstrap(
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Create the configured Snowflake database, schema, and review snapshot table.
    """
    return await sf_repository.bootstrap_database_and_schema(include_tables=True)


@router.post("/db/reviews/ikea")
async def scrape_and_persist_reviews_ikea(
    request: FetchRequest,
    ikea_scraper: ReviewsScraper = Depends(_get_ikea_scraper),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Scrape IKEA reviews and persist the latest snapshot in Snowflake.
    """
    result, snapshot_event_id = await _scrape_and_append_ikea_reviews(
        request.url,
        ikea_scraper,
        sf_repository,
    )
    return {
        "success": True,
        "snapshot_event_id": snapshot_event_id,
        "product_url": result.product_url,
        "reviews_count": result.reviews_count,
    }


@router.post("/db/reviews/latest")
async def get_latest_persisted_reviews(
    request: FetchRequest,
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Fetch the latest persisted review scrape for a product URL.
    """
    return await sf_repository.get_latest_snapshot(request.url)


@router.post("/db/reviews/recent")
async def get_recent_persisted_reviews(
    request: RecentFetchRequest,
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Fetch recent persisted review scrape snapshots for a product URL as DTOs.
    """
    return await sf_repository.list_snapshots(request.url, limit=request.limit)


@router.post("/reviews/ikea")
async def scrape_reviews_ikea(
    request: FetchRequest,
    ikea_scraper: ReviewsScraper = Depends(_get_ikea_scraper),
):
    """
    IKEA PDP review scrape using SSR review cards.
    """
    result = await _scrape_ikea_reviews(request.url, ikea_scraper)
    ikea_scraper.render_result(result)
    return result

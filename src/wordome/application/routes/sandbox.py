from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from wordome.domain import (
    ReviewsScraper,
    SitemapCrawlRecordObservation,
    SitemapPdpDiscoverer,
)
from wordome.domain.demo import ReviewSectionDetector
from wordome.infrastructure import (
    ReviewsScraperIkea,
    SitemapPdpDiscovererService,
    WebFetcher,
)
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher = WebFetcher()
review_detector = ReviewSectionDetector()


def _get_repository(request: Request) -> SnowflakeRepository:
    repository = getattr(request.app.state, "snowflake_repository", None)
    if repository is None:
        repository = SnowflakeRepository()
        request.app.state.snowflake_repository = repository
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
            "/discover/pdp-links",
            "/discover/pdp-links/dump",
            "/db/discover/pdp-links/dump",
            "/db/discover/pdp-links/scrape-reviews",
            "/reviews/ikea",
            "/db/ping",
            "/db/health",
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


class SitemapDiscoveryRequest(BaseModel):
    sitemap_url: str | None = None
    retailer_name: str | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    max_depth: int | None = None
    max_sitemaps: int | None = None


class SitemapDiscoveryDumpRequest(SitemapDiscoveryRequest):
    output_path: str | None = None


class SitemapReviewScrapeRequest(BaseModel):
    retailer_name: str
    limit: int = 10
    only_unscraped: bool = True


def _get_ikea_scraper(request: Request) -> ReviewsScraper:
    scraper = getattr(request.app.state, "ikea_scraper", None)
    if not isinstance(scraper, ReviewsScraperIkea):
        raise RuntimeError("IKEA scraper is not configured on app.state")
    return scraper


def _get_sitemap_pdp_discoverer(request: Request) -> SitemapPdpDiscoverer:
    discoverer = getattr(request.app.state, "sitemap_pdp_discoverer", None)
    if not isinstance(discoverer, SitemapPdpDiscovererService):
        raise RuntimeError("Sitemap PDP discoverer is not configured on app.state")
    return discoverer


def _resolve_reviews_scraper_for_retailer(
    retailer_name: str,
    request: Request,
) -> ReviewsScraper:
    normalized_name = retailer_name.strip().lower()
    if normalized_name in {"ikea", "ikea_us"}:
        return _get_ikea_scraper(request)
    raise HTTPException(
        status_code=400,
        detail=f"No reviews scraper is configured for retailer `{retailer_name}`.",
    )


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


def _build_sitemap_dump_lines(result) -> list[str]:
    lines = [
        f"# retailer_name: {result.retailer_name}",
        f"# entrypoint_url: {result.entrypoint_url}",
        f"# pdp_url_count: {len(result.pdp_urls)}",
        f"# processed_sitemaps_count: {len(result.processed_sitemaps)}",
        f"# skipped_sitemaps_count: {len(result.skipped_sitemaps)}",
        f"# errors_count: {len(result.errors)}",
        "#",
    ]
    lines.extend(result.pdp_urls)
    return lines


def _default_sitemap_dump_path(request: SitemapDiscoveryDumpRequest) -> Path:
    retailer_part = request.retailer_name or "custom"
    return Path(
        f"/Users/pototo/codebase/wordome/src/wordome/resources/{retailer_part}_pdp_links.txt"
    )


def _dedupe_crawl_record_observations(
    observations: list[SitemapCrawlRecordObservation],
) -> list[SitemapCrawlRecordObservation]:
    deduped: dict[tuple[str, str], SitemapCrawlRecordObservation] = {}
    for observation in observations:
        key = (observation.record_type, observation.record_url)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = observation
            continue
        # Preserve the strongest crawl outcome, and on ties keep the later
        # observation so stateful fields like parent_url/depth stay current.
        if _observation_priority(observation) >= _observation_priority(existing):
            deduped[key] = observation
    return list(deduped.values())


def _observation_priority(observation: SitemapCrawlRecordObservation) -> int:
    """
    Rank duplicate observations for the same (record_type, record_url).

    Higher numbers represent stronger crawl outcomes:
    - error: fetch/parse failures should override later weaker signals
    - processed/discovered: successful sitemap or accepted leaf outcomes
    - skipped: meaningful skips such as pattern/depth/limit filtering
    - already_seen: weakest signal because it is only duplicate noise

    When two observations have the same priority, the later one wins so
    stateful fields like parent_url and depth reflect the most recently
    observed crawl context within the run.
    """
    if observation.record_status == "error":
        return 4
    if observation.record_status in {"processed", "discovered"}:
        return 3
    if observation.skip_reason == "already_seen":
        return 1
    return 2


async def _discover_pdp_links(
    request: SitemapDiscoveryRequest,
    discoverer: SitemapPdpDiscoverer,
    record_observer=None,
):
    try:
        return await discoverer.discover_pdp_urls(
            request.sitemap_url,
            retailer_name=request.retailer_name,
            include_patterns=request.include_patterns,
            exclude_patterns=request.exclude_patterns,
            max_depth=request.max_depth,
            max_sitemaps=request.max_sitemaps,
            record_observer=record_observer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fetch/html")
async def fetch_html(request: FetchRequest):
    """
    Fetch raw HTML for the requested URL.
    """
    return await web_fetcher.fetch(request.url)


@router.post("/discover/pdp-links")
async def discover_pdp_links(
    request: SitemapDiscoveryRequest,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
):
    """
    Traverse a public sitemap entrypoint and return candidate PDP URLs.
    """
    return await _discover_pdp_links(request, discoverer)


@router.post("/discover/pdp-links/dump")
async def discover_pdp_links_dump(
    request: SitemapDiscoveryDumpRequest,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
):
    """
    Traverse a public sitemap entrypoint, dump PDP links to a text file, and
    return the output file path plus crawl metadata.
    """
    result = await _discover_pdp_links(request, discoverer)
    output_path = (
        Path(request.output_path)
        if request.output_path
        else _default_sitemap_dump_path(request)
    )
    output_path.write_text(
        "\n".join(_build_sitemap_dump_lines(result)) + "\n",
        encoding="utf-8",
    )
    return {
        "success": True,
        "output_path": str(output_path),
        "retailer_name": result.retailer_name,
        "entrypoint_url": result.entrypoint_url,
        "pdp_url_count": len(result.pdp_urls),
        "processed_sitemaps_count": len(result.processed_sitemaps),
        "skipped_sitemaps_count": len(result.skipped_sitemaps),
        "errors_count": len(result.errors),
    }


@router.post("/db/discover/pdp-links/dump")
async def discover_pdp_links_dump_and_persist(
    request: SitemapDiscoveryDumpRequest,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Traverse a public sitemap entrypoint, dump PDP links to a text file, and
    persist crawl run bookkeeping records in Snowflake.
    """
    crawl_observations: list[SitemapCrawlRecordObservation] = []
    result = None
    try:
        entrypoint_url = discoverer.resolve_entrypoint_url(
            request.sitemap_url,
            retailer_name=request.retailer_name,
        )
        retailer_name = discoverer.resolve_retailer_name(request.retailer_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    retailer_name = retailer_name or "custom"
    crawl_run_id = await sf_repository.create_sitemap_crawl_run(
        retailer_name=retailer_name,
        entrypoint_url=entrypoint_url,
    )
    try:
        result = await _discover_pdp_links(
            request,
            discoverer,
            record_observer=crawl_observations.append,
        )
        output_path = (
            Path(request.output_path)
            if request.output_path
            else _default_sitemap_dump_path(request)
        )
        output_path.write_text(
            "\n".join(_build_sitemap_dump_lines(result)) + "\n",
            encoding="utf-8",
        )

        deduped_observations = _dedupe_crawl_record_observations(crawl_observations)
        record_write_counts = await sf_repository.upsert_sitemap_crawl_records(
            crawl_run_id=crawl_run_id,
            retailer_name=retailer_name,
            records=deduped_observations,
        )
        await sf_repository.finalize_sitemap_crawl_run(
            crawl_run_id=crawl_run_id,
            result=result,
        )
    except Exception:
        with suppress(Exception):
            await sf_repository.fail_sitemap_crawl_run(
                crawl_run_id=crawl_run_id,
                result=result,
            )
        raise

    return {
        "success": True,
        "crawl_run_id": crawl_run_id,
        **record_write_counts,
        "output_path": str(output_path),
        "retailer_name": result.retailer_name,
        "entrypoint_url": result.entrypoint_url,
        "pdp_url_count": len(result.pdp_urls),
        "processed_sitemaps_count": len(result.processed_sitemaps),
        "skipped_sitemaps_count": len(result.skipped_sitemaps),
        "errors_count": len(result.errors),
    }


@router.post("/db/discover/pdp-links/scrape-reviews")
async def scrape_reviews_from_discovered_pdp_links(
    request: SitemapReviewScrapeRequest,
    http_request: Request,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Pull retailer PDP URLs from persisted sitemap crawl records, run the review
    scraper for each selected URL, and persist resulting review snapshots.
    """
    try:
        retailer_name = (
            discoverer.resolve_retailer_name(request.retailer_name)
            or request.retailer_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scraper = _resolve_reviews_scraper_for_retailer(retailer_name, http_request)
    pdp_urls = await sf_repository.list_pdp_urls_for_review_scrape(
        retailer_name=retailer_name,
        limit=request.limit,
        only_unscraped=request.only_unscraped,
    )

    results: list[dict[str, str | int | bool | None]] = []
    success_count = 0
    failure_count = 0

    for pdp_url in pdp_urls:
        try:
            scrape_result, snapshot_event_id = await _scrape_and_append_ikea_reviews(
                pdp_url,
                scraper,
                sf_repository,
            )
        except Exception as exc:
            failure_count += 1
            results.append(
                {
                    "product_url": pdp_url,
                    "success": False,
                    "error": str(exc),
                }
            )
            continue

        success_count += 1
        results.append(
            {
                "product_url": pdp_url,
                "success": True,
                "snapshot_event_id": snapshot_event_id,
                "reviews_count": scrape_result.reviews_count,
                "review_page_url": scrape_result.review_page_url,
            }
        )

    return {
        "success": failure_count == 0,
        "retailer_name": retailer_name,
        "selected_pdp_url_count": len(pdp_urls),
        "processed_pdp_url_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "only_unscraped": request.only_unscraped,
        "results": results,
    }


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

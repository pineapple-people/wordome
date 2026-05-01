from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from wordome.domain import SitemapPdpDiscoverer
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository

from .sandbox import (
    _get_repository,
    _get_sitemap_pdp_discoverer,
    _resolve_reviews_scraper_for_retailer,
    _scrape_and_append_ikea_reviews,
    _scrape_ikea_reviews,
)

router = APIRouter(tags=["reviews"])


class RetailerReviewScrapeRequest(BaseModel):
    retailer_name: str
    limit: int = 10
    only_unscraped: bool = True


class AdHocReviewScrapeRequest(BaseModel):
    retailer_name: str
    product_url: str
    persist_result: bool = True


@router.post("/review-scrapes/crawl")
async def create_review_scrape_from_crawl(
    request: RetailerReviewScrapeRequest,
    http_request: Request,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Pull crawl-derived PDP URLs for the retailer and run the review scraping
    pipeline against the selected crawl-derived PDP URLs.
    """
    try:
        resolved_retailer_name = (
            discoverer.resolve_retailer_name(request.retailer_name)
            or request.retailer_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scraper = _resolve_reviews_scraper_for_retailer(
        resolved_retailer_name,
        http_request,
    )
    pdp_urls = await sf_repository.list_pdp_urls_for_review_scrape(
        retailer_name=resolved_retailer_name,
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
        "retailer_name": resolved_retailer_name,
        "selected_pdp_url_count": len(pdp_urls),
        "processed_pdp_url_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "only_unscraped": request.only_unscraped,
        "results": results,
    }


@router.post("/review-scrapes/single")
async def create_single_review_scrape(
    request: AdHocReviewScrapeRequest,
    http_request: Request,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Scrape a single PDP URL for ad-hoc processing outside the canonical
    crawl-to-review batch pipeline.
    """
    try:
        resolved_retailer_name = (
            discoverer.resolve_retailer_name(request.retailer_name)
            or request.retailer_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scraper = _resolve_reviews_scraper_for_retailer(
        resolved_retailer_name,
        http_request,
    )
    if request.persist_result:
        scrape_result, snapshot_event_id = await _scrape_and_append_ikea_reviews(
            request.product_url,
            scraper,
            sf_repository,
        )
    else:
        scrape_result = await _scrape_ikea_reviews(request.product_url, scraper)
        snapshot_event_id = None

    return {
        "success": True,
        "retailer_name": resolved_retailer_name,
        "product_url": scrape_result.product_url,
        "review_page_url": scrape_result.review_page_url,
        "reviews_count": scrape_result.reviews_count,
        "snapshot_event_id": snapshot_event_id,
        "persist_result": request.persist_result,
    }

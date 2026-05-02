from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from wordome.domain import SitemapPdpDiscoverer
from wordome.infrastructure.database.review_scrape_orm import (
    ReviewScrapeQueueStatus,
    ReviewScrapeRunTriggerType,
)
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


class AdHocReviewScrapeRequest(BaseModel):
    retailer_name: str
    product_url: str
    persist_result: bool = True


@router.get("/review-scrape-queue")
async def get_review_scrape_queue(
    retailer_name: str | None = Query(default=None),
    queue_status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=500),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Inspect queue rows in the sitemap-to-review handoff layer.
    """
    if queue_status is not None and queue_status not in {
        ReviewScrapeQueueStatus.UNCLAIMED.value,
        ReviewScrapeQueueStatus.CLAIMED.value,
        ReviewScrapeQueueStatus.COMPLETED.value,
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid queue_status. Expected one of: unclaimed, claimed, completed."
            ),
        )

    queue_view = await sf_repository.list_review_scrape_queue_records(
        retailer_name=retailer_name,
        queue_status=queue_status,
        limit=limit,
    )
    return {
        "retailer_name": retailer_name,
        "queue_status": queue_status,
        "item_limit": limit,
        "item_count_returned": len(queue_view["items"]),
        "item_count_total": queue_view["item_count_total"],
        "items": queue_view["items"],
    }


@router.get("/review-scrape-queue/summary")
async def get_review_scrape_queue_summary(
    retailer_name: str | None = Query(default=None),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Return aggregate counts for the review scrape queue.
    """
    return await sf_repository.summarize_review_scrape_queue(
        retailer_name=retailer_name
    )


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
    review_scrape_run_id = await sf_repository.create_review_scrape_run(
        retailer_name=resolved_retailer_name,
        trigger_type=ReviewScrapeRunTriggerType.CRAWL.value,
    )
    pdp_urls = await sf_repository.claim_review_scrape_queue_urls(
        retailer_name=resolved_retailer_name,
        limit=request.limit,
        review_scrape_run_id=review_scrape_run_id,
    )
    await sf_repository.update_review_scrape_run_selected_count(
        review_scrape_run_id=review_scrape_run_id,
        selected_url_count=len(pdp_urls),
    )

    results: list[dict[str, str | int | bool | None]] = []
    success_count = 0
    failure_count = 0

    try:
        for pdp_url in pdp_urls:
            try:
                (
                    scrape_result,
                    snapshot_event_id,
                ) = await _scrape_and_append_ikea_reviews(
                    pdp_url,
                    scraper,
                    sf_repository,
                )
                await sf_repository.mark_review_scrape_queue_completed(
                    retailer_name=resolved_retailer_name,
                    product_url=pdp_url,
                )
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
            except Exception as exc:
                failure_count += 1
                await sf_repository.record_review_scrape_queue_failure(
                    retailer_name=resolved_retailer_name,
                    product_url=pdp_url,
                    latest_error_message=str(exc),
                )
                results.append(
                    {
                        "product_url": pdp_url,
                        "success": False,
                        "error": str(exc),
                    }
                )
                continue
        await sf_repository.finalize_review_scrape_run(
            review_scrape_run_id=review_scrape_run_id,
            success_count=success_count,
            failure_count=failure_count,
        )
    except Exception:
        await sf_repository.fail_review_scrape_run(
            review_scrape_run_id=review_scrape_run_id,
            success_count=success_count,
            failure_count=failure_count,
        )
        raise

    return {
        "success": failure_count == 0,
        "review_scrape_run_id": review_scrape_run_id,
        "retailer_name": resolved_retailer_name,
        "selected_pdp_url_count": len(pdp_urls),
        "processed_pdp_url_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
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
        review_scrape_run_id = await sf_repository.create_review_scrape_run(
            retailer_name=resolved_retailer_name,
            trigger_type=ReviewScrapeRunTriggerType.SINGLE.value,
            selected_url_count=1,
        )
        try:
            scrape_result, snapshot_event_id = await _scrape_and_append_ikea_reviews(
                request.product_url,
                scraper,
                sf_repository,
            )
            await sf_repository.finalize_review_scrape_run(
                review_scrape_run_id=review_scrape_run_id,
                success_count=1,
                failure_count=0,
            )
        except Exception:
            await sf_repository.fail_review_scrape_run(
                review_scrape_run_id=review_scrape_run_id,
                success_count=0,
                failure_count=1,
            )
            raise
    else:
        review_scrape_run_id = None
        scrape_result = await _scrape_ikea_reviews(request.product_url, scraper)
        snapshot_event_id = None

    return {
        "success": True,
        "review_scrape_run_id": review_scrape_run_id,
        "retailer_name": resolved_retailer_name,
        "product_url": scrape_result.product_url,
        "review_page_url": scrape_result.review_page_url,
        "reviews_count": scrape_result.reviews_count,
        "snapshot_event_id": snapshot_event_id,
        "persist_result": request.persist_result,
    }

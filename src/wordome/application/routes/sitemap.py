from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from wordome.domain import SitemapCrawlRecordObservation, SitemapPdpDiscoverer
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository

from .sandbox import (
    _dedupe_crawl_record_observations,
    _discover_pdp_links,
    _get_repository,
    _get_sitemap_pdp_discoverer,
)

router = APIRouter(tags=["sitemap"])


class RetailerSitemapCrawlRequest(BaseModel):
    retailer_name: str
    sitemap_url: str | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    max_depth: int | None = None
    max_sitemaps: int | None = None


@router.post("/sitemap-crawls")
async def create_sitemap_crawl(
    request: RetailerSitemapCrawlRequest,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Run a sitemap crawl for the retailer, defaulting to the configured
    codebase sitemap entrypoint when an explicit sitemap URL is not provided.
    """
    crawl_observations: list[SitemapCrawlRecordObservation] = []
    result = None

    try:
        entrypoint_url = discoverer.resolve_entrypoint_url(
            request.sitemap_url,
            retailer_name=request.retailer_name,
        )
        resolved_retailer_name = (
            discoverer.resolve_retailer_name(request.retailer_name)
            or request.retailer_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    crawl_run_id = await sf_repository.create_sitemap_crawl_run(
        retailer_name=resolved_retailer_name,
        entrypoint_url=entrypoint_url,
    )

    try:
        result = await _discover_pdp_links(
            request,
            discoverer,
            record_observer=crawl_observations.append,
        )
        deduped_observations = _dedupe_crawl_record_observations(crawl_observations)
        record_write_counts = await sf_repository.upsert_sitemap_crawl_records(
            crawl_run_id=crawl_run_id,
            retailer_name=resolved_retailer_name,
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
        "retailer_name": result.retailer_name,
        "entrypoint_url": result.entrypoint_url,
        "pdp_url_count": len(result.pdp_urls),
        "processed_sitemaps_count": len(result.processed_sitemaps),
        "skipped_sitemaps_count": len(result.skipped_sitemaps),
        "errors_count": len(result.errors),
    }

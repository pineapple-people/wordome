import asyncio
from contextlib import suppress

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from wordome.domain import SitemapCrawlRecordObservation, SitemapPdpDiscoverer
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository
from wordome.support import TraceMode, create_trace

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


async def _persist_sitemap_crawl_results(
    *,
    crawl_run_id: str,
    resolved_retailer_name: str,
    result,
    crawl_observations: list[SitemapCrawlRecordObservation],
    discoverer: SitemapPdpDiscoverer,
    sf_repository: SnowflakeRepository,
) -> None:
    trace_mode = getattr(discoverer, "trace_mode", TraceMode.OFF)
    trace = create_trace(
        "SitemapPersistencePipeline",
        trace_mode,
    )
    deduped_observations = _dedupe_crawl_record_observations(crawl_observations)
    trace.start()
    try:
        trace.callout("identified crawl result items", str(len(deduped_observations)))
        with trace.step(
            f"writing to table: {sf_repository.SITEMAP_CRAWL_RECORDS_TABLE}"
        ):
            await sf_repository.upsert_sitemap_crawl_records(
                crawl_run_id=crawl_run_id,
                retailer_name=resolved_retailer_name,
                records=deduped_observations,
                batch_progress_callback=lambda current, total, size: trace.callout(
                    "batch",
                    f"{current}/{total} ({size} records)",
                ),
            )
        with trace.step(f"writing to table: {sf_repository.REVIEW_SCRAPE_QUEUE_TABLE}"):
            await sf_repository.enqueue_review_scrape_urls(
                retailer_name=resolved_retailer_name,
                product_urls=result.pdp_urls,
                batch_progress_callback=lambda current, total, size: trace.callout(
                    "batch",
                    f"{current}/{total} ({size} urls)",
                ),
            )
        with trace.step(f"writing to table: {sf_repository.SITEMAP_CRAWL_RUNS_TABLE}"):
            await sf_repository.finalize_sitemap_crawl_run(
                crawl_run_id=crawl_run_id,
                result=result,
            )
    finally:
        trace.stop()


async def _run_sitemap_crawl_in_background(
    request: RetailerSitemapCrawlRequest,
    *,
    crawl_run_id: str,
    resolved_retailer_name: str,
    discoverer: SitemapPdpDiscoverer,
    sf_repository: SnowflakeRepository,
) -> None:
    crawl_observations: list[SitemapCrawlRecordObservation] = []
    result = None
    try:
        result = await _discover_pdp_links(
            request,
            discoverer,
            record_observer=crawl_observations.append,
        )
        await _persist_sitemap_crawl_results(
            crawl_run_id=crawl_run_id,
            resolved_retailer_name=resolved_retailer_name,
            result=result,
            crawl_observations=crawl_observations,
            discoverer=discoverer,
            sf_repository=sf_repository,
        )
    except asyncio.CancelledError:
        # Shutdown can cancel an in-flight background crawl.
        with suppress(Exception):
            await sf_repository.fail_sitemap_crawl_run(
                crawl_run_id=crawl_run_id,
                result=result,
            )
        return
    except Exception:
        with suppress(Exception):
            await sf_repository.fail_sitemap_crawl_run(
                crawl_run_id=crawl_run_id,
                result=result,
            )
        raise


@router.post("/sitemap-crawls")
async def create_sitemap_crawl(
    request: RetailerSitemapCrawlRequest,
    background_tasks: BackgroundTasks,
    discoverer: SitemapPdpDiscoverer = Depends(_get_sitemap_pdp_discoverer),
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Kick off a sitemap crawl for the retailer, defaulting to the configured
    codebase sitemap entrypoint when an explicit sitemap URL is not provided.
    """
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

    background_tasks.add_task(
        _run_sitemap_crawl_in_background,
        request,
        crawl_run_id=crawl_run_id,
        resolved_retailer_name=resolved_retailer_name,
        discoverer=discoverer,
        sf_repository=sf_repository,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "success": True,
            "crawl_run_id": crawl_run_id,
            "retailer_name": resolved_retailer_name,
            "entrypoint_url": entrypoint_url,
            "status": "running",
        },
    )


@router.get("/sitemap-crawls/{crawl_run_id}")
async def get_sitemap_crawl_status(
    crawl_run_id: str,
    sf_repository: SnowflakeRepository = Depends(_get_repository),
):
    """
    Retrieve the current status and summary counts for a sitemap crawl run.
    """
    result = await sf_repository.get_sitemap_crawl_run(crawl_run_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sitemap crawl run not found: {crawl_run_id}",
        )
    return result

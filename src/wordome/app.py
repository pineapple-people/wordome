import uvicorn
from fastapi import FastAPI

from wordome.application.routes import health, reviews, sandbox, sitemap
from wordome.infrastructure import ReviewsScraperIkea, SitemapDiscovererService
from wordome.support import TraceMode


def create_app(trace_mode: TraceMode = TraceMode.LIVE) -> FastAPI:
    app = FastAPI(
        title="Wordome API",
        description="Web scraping and word frequency analysis",
    )
    app.state.ikea_scraper = ReviewsScraperIkea(trace_mode=trace_mode)
    app.state.sitemap_pdp_discoverer = SitemapDiscovererService(trace_mode=trace_mode)
    app.include_router(health.router)
    app.include_router(sitemap.router)
    app.include_router(reviews.router)
    app.include_router(sandbox.router)
    return app


app = create_app()

if __name__ == "__main__":
    """
    Standalone execution for debugging purposes only
    """
    uvicorn.run(app, host="127.0.0.1", port=8000)

from fastapi import APIRouter
from pydantic import BaseModel

from wordome.infrastructure import WebFetcherManager

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher_manager = WebFetcherManager()


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


@router.get("/headers")
async def headers():
    """
    Show request headers (generated via curl_cffi)
    Note: unique variation generated per request
    """
    return await web_fetcher_manager.fetch_header_async()


class FetchRequest(BaseModel):
    url: str


@router.post("/fetch_html")
async def fetch_html(request: FetchRequest):
    """
    Get HTML for a given URL
    """
    return await web_fetcher_manager.fetch_async(request.url)

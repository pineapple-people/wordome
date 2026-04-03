from fastapi import APIRouter
from pydantic import BaseModel

from wordome.infrastructure import WebFetcher

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
web_fetcher = WebFetcher()


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

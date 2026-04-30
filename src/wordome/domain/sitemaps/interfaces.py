from collections.abc import Callable
from typing import Protocol

from .models import SitemapCrawlRecordObservation, SitemapPdpDiscoveryResult


class SitemapPdpDiscoverer(Protocol):
    def resolve_retailer_name(self, retailer_name: str | None = None) -> str | None: ...

    def resolve_entrypoint_url(
        self,
        sitemap_url: str | None = None,
        *,
        retailer_name: str | None = None,
    ) -> str: ...

    async def discover_pdp_urls(
        self,
        sitemap_url: str | None = None,
        *,
        retailer_name: str | None = None,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_depth: int | None = None,
        max_sitemaps: int | None = None,
        record_observer: Callable[[SitemapCrawlRecordObservation], None] | None = None,
    ) -> SitemapPdpDiscoveryResult: ...

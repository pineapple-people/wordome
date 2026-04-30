from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetailerSitemapProfile:
    name: str
    entrypoint_url: str
    sitemap_include_patterns: list[str] = field(default_factory=list)
    sitemap_exclude_patterns: list[str] = field(default_factory=list)
    pdp_include_patterns: list[str] = field(default_factory=list)
    pdp_exclude_patterns: list[str] = field(default_factory=list)
    same_host_only: bool = True
    max_depth: int = 3
    max_sitemaps: int = 50


@dataclass(frozen=True)
class SitemapTraversalStats:
    discovered_sitemaps: int = 0
    processed_sitemaps: int = 0
    discovered_urls: int = 0
    matched_pdp_urls: int = 0
    max_depth_reached: int = 0


@dataclass(frozen=True)
class SitemapCrawlRecordObservation:
    record_url: str
    parent_url: str | None = None
    record_type: str = "sitemap_document"
    url_type: str | None = None
    depth: int | None = None
    record_status: str = "processed"
    skip_reason: str | None = None
    child_sitemap_count: int | None = None
    child_url_count: int | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class SitemapPdpDiscoveryResult:
    entrypoint_url: str
    retailer_name: str | None = None
    pdp_urls: list[str] = field(default_factory=list)
    processed_sitemaps: list[str] = field(default_factory=list)
    skipped_sitemaps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stats: SitemapTraversalStats = field(default_factory=SitemapTraversalStats)

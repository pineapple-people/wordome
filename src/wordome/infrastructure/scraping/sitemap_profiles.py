from wordome.domain.sitemaps import RetailerSitemapProfile, SupportedRetailer

IKEA_US_PROFILE = RetailerSitemapProfile(
    name=SupportedRetailer.IKEA_US,
    entrypoint_url="https://www.ikea.com/sitemaps/sitemap.xml",
    sitemap_include_patterns=[r"prod-en-US_[^/]+\.xml$"],
    pdp_include_patterns=[r"/p/"],
    pdp_exclude_patterns=[r"/services/", r"/inspiration/"],
    same_host_only=True,
    max_depth=3,
    max_sitemaps=50,
)

SITEMAP_PROFILES: dict[str, RetailerSitemapProfile] = {
    SupportedRetailer.IKEA_US.value: IKEA_US_PROFILE,
    "ikea": IKEA_US_PROFILE,
}

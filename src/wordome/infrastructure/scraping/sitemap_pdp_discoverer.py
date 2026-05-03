import re
from collections import deque
from collections.abc import Callable
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup, FeatureNotFound

from wordome.domain.sitemaps import (
    RetailerSitemapProfile,
    SitemapCrawlRecordObservation,
    SitemapPdpDiscoveryResult,
    SitemapTraversalStats,
)
from wordome.support import TraceMode, create_trace

from .sitemap_profiles import SITEMAP_PROFILES
from .web_fetcher import WebFetcher


class SitemapDiscovererService:
    """
    Discover candidate PDP URLs by traversing public sitemap XML documents.

    The public contract stays generic while retailer-specific rules are
    provided through lightweight profiles.
    """

    DEFAULT_PDP_INCLUDE_PATTERNS = (
        r"/p/",
        r"/product/",
        r"/products/",
        r"/dp/",
        r"/item/",
    )
    DEFAULT_PDP_EXCLUDE_PATTERNS = (
        r"/blog/",
        r"/category/",
        r"/collections/",
        r"/search",
        r"/cart",
        r"/account",
    )

    def __init__(
        self,
        web_fetcher: WebFetcher | None = None,
        profiles: dict[str, RetailerSitemapProfile] | None = None,
        trace_mode: TraceMode = TraceMode.OFF,
    ) -> None:
        self._web_fetcher = web_fetcher or WebFetcher()
        self._profiles = profiles or SITEMAP_PROFILES
        self.trace_mode = trace_mode

    def set_trace_mode(self, trace_mode: TraceMode) -> None:
        self.trace_mode = trace_mode

    def _create_trace(self):
        return create_trace(
            self.__class__.__name__,
            self.trace_mode,
        )

    def resolve_entrypoint_url(
        self,
        sitemap_url: str | None = None,
        *,
        retailer_name: str | None = None,
    ) -> str:
        profile = self._resolve_profile(retailer_name)
        effective_sitemap_url = sitemap_url or (
            profile.entrypoint_url if profile else None
        )
        if not effective_sitemap_url:
            raise ValueError("sitemap_url or retailer_name is required")
        return effective_sitemap_url

    def resolve_retailer_name(self, retailer_name: str | None = None) -> str | None:
        profile = self._resolve_profile(retailer_name)
        if profile is None:
            return retailer_name
        return profile.name.value

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
    ) -> SitemapPdpDiscoveryResult:
        trace = self._create_trace()
        profile = self._resolve_profile(retailer_name)
        effective_sitemap_url = self.resolve_entrypoint_url(
            sitemap_url,
            retailer_name=retailer_name,
        )

        effective_max_depth = (
            max_depth
            if max_depth is not None
            else (profile.max_depth if profile else None)
        )
        effective_max_sitemaps = (
            max_sitemaps
            if max_sitemaps is not None
            else (profile.max_sitemaps if profile else 50)
        )

        include_regexes = self._compile_patterns(
            include_patterns
            if include_patterns is not None
            else self._resolve_pdp_include_patterns(profile)
        )
        exclude_regexes = self._compile_patterns(
            exclude_patterns
            if exclude_patterns is not None
            else self._resolve_pdp_exclude_patterns(profile)
        )
        sitemap_include_regexes = self._compile_patterns(
            profile.sitemap_include_patterns if profile else []
        )
        sitemap_exclude_regexes = self._compile_patterns(
            profile.sitemap_exclude_patterns if profile else []
        )

        queue: deque[tuple[str, int, str | None]] = deque(
            [(effective_sitemap_url, 0, None)]
        )
        visited_sitemaps: set[str] = set()
        processed_sitemaps: list[str] = []
        skipped_sitemaps: list[str] = []
        errors: list[str] = []
        pdp_urls: set[str] = set()
        discovered_urls = 0
        max_depth_reached = 0
        root_host = urlparse(effective_sitemap_url).netloc.lower()
        trace.start()
        try:
            trace.message(
                f"starting sitemap crawl: {effective_sitemap_url}",
                level="info",
            )
            trace.callout(
                "retailer",
                profile.name.value if profile else (retailer_name or "custom"),
            )
            trace.callout(
                "max_depth",
                str(effective_max_depth)
                if effective_max_depth is not None
                else "(unbounded)",
            )
            trace.callout("max_sitemaps", str(effective_max_sitemaps))
            trace.callout(
                "pdp include patterns",
                self._format_patterns(include_regexes),
            )
            trace.callout(
                "pdp exclude patterns",
                self._format_patterns(exclude_regexes),
            )
            trace.callout(
                "sitemap include patterns",
                self._format_patterns(sitemap_include_regexes),
            )
            trace.callout(
                "sitemap exclude patterns",
                self._format_patterns(sitemap_exclude_regexes),
            )

            with trace.step("total crawl"):
                while queue and len(processed_sitemaps) < effective_max_sitemaps:
                    current_sitemap_url, depth, parent_url = queue.popleft()
                    normalized_sitemap_url = self._normalize_url(current_sitemap_url)

                    with trace.step(f"sitemap depth {depth}: {normalized_sitemap_url}"):
                        if normalized_sitemap_url in visited_sitemaps:
                            trace.message("already seen; skipping", level="warn")
                            self._observe(
                                record_observer,
                                SitemapCrawlRecordObservation(
                                    record_url=normalized_sitemap_url,
                                    parent_url=parent_url,
                                    record_type="sitemap_document",
                                    depth=depth,
                                    record_status="skipped",
                                    skip_reason="already_seen",
                                ),
                            )
                            continue

                        visited_sitemaps.add(normalized_sitemap_url)
                        max_depth_reached = max(max_depth_reached, depth)
                        if (
                            effective_max_depth is not None
                            and depth > effective_max_depth
                        ):
                            trace.message("depth limit reached; skipping", level="warn")
                            skipped_sitemaps.append(normalized_sitemap_url)
                            self._observe(
                                record_observer,
                                SitemapCrawlRecordObservation(
                                    record_url=normalized_sitemap_url,
                                    parent_url=parent_url,
                                    record_type="sitemap_document",
                                    depth=depth,
                                    record_status="skipped",
                                    skip_reason="depth_limit",
                                ),
                            )
                            continue

                        with trace.step("fetch sitemap xml"):
                            xml_text = await self._web_fetcher.fetch(
                                normalized_sitemap_url
                            )
                        if not xml_text:
                            trace.message("fetch failed", level="error")
                            errors.append(
                                f"failed to fetch sitemap: {normalized_sitemap_url}"
                            )
                            self._observe(
                                record_observer,
                                SitemapCrawlRecordObservation(
                                    record_url=normalized_sitemap_url,
                                    parent_url=parent_url,
                                    record_type="sitemap_document",
                                    depth=depth,
                                    record_status="error",
                                    last_error_message="failed to fetch sitemap",
                                ),
                            )
                            continue

                        with trace.step("parse sitemap xml"):
                            parsed_sitemap = self._parse_sitemap(xml_text)
                        if parsed_sitemap is None:
                            trace.message("parse failed", level="error")
                            errors.append(
                                f"failed to parse sitemap: {normalized_sitemap_url}"
                            )
                            self._observe(
                                record_observer,
                                SitemapCrawlRecordObservation(
                                    record_url=normalized_sitemap_url,
                                    parent_url=parent_url,
                                    record_type="sitemap_document",
                                    depth=depth,
                                    record_status="error",
                                    last_error_message="failed to parse sitemap",
                                ),
                            )
                            continue

                        processed_sitemaps.append(normalized_sitemap_url)
                        trace.message(
                            f"parsed {len(parsed_sitemap['sitemaps'])} child sitemaps and "
                            f"{len(parsed_sitemap['urls'])} urls",
                            level="info",
                        )
                        self._observe(
                            record_observer,
                            SitemapCrawlRecordObservation(
                                record_url=normalized_sitemap_url,
                                parent_url=parent_url,
                                record_type="sitemap_document",
                                depth=depth,
                                record_status="processed",
                                child_sitemap_count=len(parsed_sitemap["sitemaps"]),
                                child_url_count=len(parsed_sitemap["urls"]),
                            ),
                        )

                        enqueued_sitemaps = 0
                        skipped_child_sitemaps = 0
                        for nested_sitemap_url in parsed_sitemap["sitemaps"]:
                            normalized_nested = self._normalize_url(nested_sitemap_url)
                            should_follow, skip_reason = self._should_follow_sitemap(
                                normalized_nested,
                                root_host=root_host,
                                same_host_only=profile.same_host_only
                                if profile
                                else True,
                                include_regexes=sitemap_include_regexes,
                                exclude_regexes=sitemap_exclude_regexes,
                            )
                            if should_follow:
                                queue.append(
                                    (
                                        normalized_nested,
                                        depth + 1,
                                        normalized_sitemap_url,
                                    )
                                )
                                enqueued_sitemaps += 1
                            else:
                                skipped_child_sitemaps += 1
                                skipped_sitemaps.append(normalized_nested)
                                self._observe(
                                    record_observer,
                                    SitemapCrawlRecordObservation(
                                        record_url=normalized_nested,
                                        parent_url=normalized_sitemap_url,
                                        record_type="sitemap_document",
                                        depth=depth + 1,
                                        record_status="skipped",
                                        skip_reason=skip_reason,
                                    ),
                                )
                        trace.callout("queued child sitemaps", str(enqueued_sitemaps))
                        if skipped_child_sitemaps:
                            trace.callout(
                                "skipped child sitemaps",
                                str(skipped_child_sitemaps),
                            )

                        matched_pdp_count = 0
                        skipped_url_count = 0
                        for candidate_url in parsed_sitemap["urls"]:
                            discovered_urls += 1
                            normalized_candidate = self._normalize_url(candidate_url)
                            if self._matches_pdp_url(
                                normalized_candidate,
                                include_regexes,
                                exclude_regexes,
                            ):
                                pdp_urls.add(normalized_candidate)
                                matched_pdp_count += 1
                                self._observe(
                                    record_observer,
                                    SitemapCrawlRecordObservation(
                                        record_url=normalized_candidate,
                                        parent_url=normalized_sitemap_url,
                                        record_type="discovered_url",
                                        url_type="pdp",
                                        depth=depth + 1,
                                        record_status="discovered",
                                    ),
                                )
                            else:
                                skipped_url_count += 1
                                self._observe(
                                    record_observer,
                                    SitemapCrawlRecordObservation(
                                        record_url=normalized_candidate,
                                        parent_url=normalized_sitemap_url,
                                        record_type="discovered_url",
                                        url_type=self._classify_url_type(
                                            normalized_candidate
                                        ),
                                        depth=depth + 1,
                                        record_status="skipped",
                                        skip_reason="non_target_url_type",
                                    ),
                                )
                        trace.callout("matched pdp urls", str(matched_pdp_count))
                        if skipped_url_count:
                            trace.callout("non-pdp urls", str(skipped_url_count))

                if queue and len(processed_sitemaps) >= effective_max_sitemaps:
                    trace.message(
                        "max_sitemaps limit reached; marking queued remainder as skipped",
                        level="warn",
                    )
                    abandoned_sitemaps: set[str] = set()
                    while queue:
                        queued_sitemap_url, depth, parent_url = queue.popleft()
                        normalized_queued = self._normalize_url(queued_sitemap_url)
                        if (
                            normalized_queued in visited_sitemaps
                            or normalized_queued in abandoned_sitemaps
                        ):
                            continue
                        abandoned_sitemaps.add(normalized_queued)
                        skipped_sitemaps.append(normalized_queued)
                        self._observe(
                            record_observer,
                            SitemapCrawlRecordObservation(
                                record_url=normalized_queued,
                                parent_url=parent_url,
                                record_type="sitemap_document",
                                depth=depth,
                                record_status="skipped",
                                skip_reason="max_sitemaps_limit",
                            ),
                        )

            trace.message(
                f"discovery complete: {len(processed_sitemaps)} processed sitemaps, "
                f"{len(pdp_urls)} pdp urls, {len(errors)} errors",
                level="info",
            )

            stats = SitemapTraversalStats(
                discovered_sitemaps=len(visited_sitemaps),
                processed_sitemaps=len(processed_sitemaps),
                discovered_urls=discovered_urls,
                matched_pdp_urls=len(pdp_urls),
                max_depth_reached=max_depth_reached,
            )
            return SitemapPdpDiscoveryResult(
                entrypoint_url=effective_sitemap_url,
                retailer_name=profile.name.value if profile else retailer_name,
                pdp_urls=sorted(pdp_urls),
                processed_sitemaps=processed_sitemaps,
                skipped_sitemaps=sorted(set(skipped_sitemaps)),
                errors=errors,
                stats=stats,
            )
        finally:
            trace.stop()

    def _resolve_profile(
        self, retailer_name: str | None
    ) -> RetailerSitemapProfile | None:
        if retailer_name is None:
            return None
        profile = self._profiles.get(retailer_name)
        if profile is None:
            raise ValueError(f"unknown retailer profile: {retailer_name}")
        return profile

    def _resolve_pdp_include_patterns(
        self, profile: RetailerSitemapProfile | None
    ) -> list[str]:
        if profile and profile.pdp_include_patterns:
            return profile.pdp_include_patterns
        return list(self.DEFAULT_PDP_INCLUDE_PATTERNS)

    def _resolve_pdp_exclude_patterns(
        self, profile: RetailerSitemapProfile | None
    ) -> list[str]:
        if profile and profile.pdp_exclude_patterns:
            return profile.pdp_exclude_patterns
        return list(self.DEFAULT_PDP_EXCLUDE_PATTERNS)

    def _should_follow_sitemap(
        self,
        url: str,
        *,
        root_host: str,
        same_host_only: bool,
        include_regexes: list[re.Pattern[str]],
        exclude_regexes: list[re.Pattern[str]],
    ) -> tuple[bool, str | None]:
        if same_host_only and not self._is_same_host(url, root_host):
            return False, "host_mismatch"
        if any(regex.search(url) for regex in exclude_regexes):
            return False, "pattern_mismatch"
        if include_regexes:
            matches_include = any(regex.search(url) for regex in include_regexes)
            return matches_include, None if matches_include else "pattern_mismatch"
        return True, None

    def _parse_sitemap(self, xml_text: str) -> dict[str, list[str]] | None:
        root = self._parse_xml_root(xml_text)
        if root is None:
            return None

        tag_name = self._strip_namespace(root.tag)
        if tag_name == "sitemapindex":
            return {
                "sitemaps": self._extract_loc_children(root, "sitemap"),
                "urls": [],
            }
        if tag_name == "urlset":
            return {
                "sitemaps": [],
                "urls": self._extract_loc_children(root, "url"),
            }

        try:
            soup = BeautifulSoup(xml_text, "xml")
        except FeatureNotFound:
            soup = BeautifulSoup(xml_text, "html.parser")
        sitemaps = [loc.get_text(strip=True) for loc in soup.select("sitemap > loc")]
        urls = [loc.get_text(strip=True) for loc in soup.select("url > loc")]
        if not sitemaps and not urls:
            return None
        return {"sitemaps": sitemaps, "urls": urls}

    def _parse_xml_root(self, xml_text: str):
        try:
            return ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return None

    def _extract_loc_children(self, root, child_tag_name: str) -> list[str]:
        values: list[str] = []
        for child in root:
            if self._strip_namespace(child.tag) != child_tag_name:
                continue
            for grandchild in child:
                if self._strip_namespace(grandchild.tag) != "loc":
                    continue
                if grandchild.text:
                    values.append(grandchild.text.strip())
        return values

    def _matches_pdp_url(
        self,
        url: str,
        include_regexes: list[re.Pattern[str]],
        exclude_regexes: list[re.Pattern[str]],
    ) -> bool:
        if any(regex.search(url) for regex in exclude_regexes):
            return False
        return any(regex.search(url) for regex in include_regexes)

    def _classify_url_type(self, url: str) -> str:
        if "/cat/" in url:
            return "category"
        return "unknown"

    def _observe(
        self,
        record_observer: Callable[[SitemapCrawlRecordObservation], None] | None,
        observation: SitemapCrawlRecordObservation,
    ) -> None:
        if record_observer is None:
            return
        record_observer(observation)

    def _compile_patterns(self, patterns: list[str]) -> list[re.Pattern[str]]:
        return [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]

    def _format_patterns(self, patterns: list[re.Pattern[str]]) -> str:
        if not patterns:
            return "(none)"
        return ", ".join(pattern.pattern for pattern in patterns)

    def _normalize_url(self, url: str) -> str:
        return url.strip()

    def _is_same_host(self, url: str, root_host: str) -> bool:
        return urlparse(url).netloc.lower() == root_host

    def _strip_namespace(self, tag: str) -> str:
        return tag.split("}", maxsplit=1)[-1]


SitemapPdpDiscovererService = SitemapDiscovererService

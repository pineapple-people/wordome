import re

from bs4 import BeautifulSoup
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from wordome.domain.reviews.models import (
    Review,
    ReviewScrapeDomainMetadata,
    ReviewScrapeMetadata,
    ReviewScrapeResult,
    ReviewSource,
)
from wordome.support import (
    RichLiveTraceLogger,
    RichTraceLogger,
    current_trace,
    use_trace,
)


class ReviewsScraperIkea:
    """
    POC scraper for IKEA PDP review collection.

    The page exposes review cards in the DOM and a dedicated "Load more" button
    in the review modal / section. We click through pagination until the button
    is exhausted, then capture the final DOM snapshot once.
    """

    # Browser and interaction defaults.
    DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
    REVIEW_MODAL_OPEN_SETTLE_MS = 500
    DEFAULT_MODAL_SETTLE_MS = 250
    REVIEW_UI_READY_TIMEOUT_MS = 2_000
    DEFAULT_MAX_LOAD_MORE_CLICKS = 20
    REVIEW_MODAL_TAB_SCOPE = ".ugc-rr-pip-fe-modal-wrapper--open"
    REVIEW_REGION_TAB_ALLOWLIST = ("United States", "Other countries")
    REVIEW_TAB_CONTROLS = ("local", "other")

    # Review card extraction selectors.
    REVIEW_CARD_SELECTORS = (
        ".ugc-rr-pip-fe-review",
        ".pipf-seo-reviews__review",
        "[class*='ugc-rr-pip-fe-reviews__review']",
    )
    REVIEW_SUMMARY_SELECTOR = ".pipf-rating__sr-only"
    REVIEW_TITLE_SELECTOR = ".ugc-rr-pip-fe-review__title, .pipf-seo-reviews__review-title, [class*='review-title']"
    REVIEW_AUTHOR_SELECTOR = ".ugc-rr-pip-fe-reviewer-name, .pipf-seo-reviews__review-name, [class*='review-name']"
    REVIEW_BODY_SELECTOR = ".ugc-rr-pip-fe-review__text, .pipf-seo-reviews__review-text, [class*='review-text']"
    REVIEW_RATING_SELECTOR = ".ugc-rr-pip-fe-rating__stars, .pipf-seo-reviews__review-ratingValue, [class*='review-ratingValue']"

    # Pagination / modal selectors.
    REVIEW_MODAL_PAGINATION_SELECTOR = "div.ugc-rr-pip-fe-reviews__load-more"
    LOAD_MORE_SELECTORS = (
        "button:has-text('Load more')",
        "button:has-text('Load More')",
        "button:has-text('More reviews')",
        "div.ugc-rr-pip-fe-reviews__load-more button",
        ".ugc-rr-pip-fe-btn.ugc-rr-pip-fe-btn--small.ugc-rr-pip-fe-btn--secondary.ugc-rr-pip-fe-reviews__load-more__button",
        "button.ugc-rr-pip-fe-reviews__load-more__button",
    )
    REVIEW_MODAL_OPENERS = (
        "div.js-ugc-container.pipf-ratings-and-qna button.pipf-rating",
        "div.js-ugc-container.pipf-ratings-and-qna > button.pipf-rating",
        "button:has-text('Show all reviews')button:has-text('Reviews')",
    )
    REVIEW_ENTRY_SELECTORS = (
        *REVIEW_MODAL_OPENERS,
        ".pipf-seo-reviews__summary",
        "[class*='review']",
    )
    REVIEW_MODAL_READY_SELECTORS = (
        REVIEW_MODAL_TAB_SCOPE,
        REVIEW_MODAL_PAGINATION_SELECTOR,
    )
    # REVIEW_API_MARKER = "web-api.ikea.com/tugc/public/v5/reviews/"

    def __init__(self, consider_other_tabs: bool = False) -> None:
        self._default_trace = RichLiveTraceLogger(self.__class__.__name__)
        self.consider_other_tabs = consider_other_tabs

    @property
    def _trace(self) -> RichTraceLogger:
        return current_trace() or self._default_trace

    async def scrape(self, product_url: str) -> ReviewScrapeResult:
        trace = RichLiveTraceLogger(self.__class__.__name__)
        html: str | None = None
        collected_reviews: list[Review] = []
        scraped_tabs: list[str] = []

        with use_trace(trace):
            trace.message(f"scraping product page: {product_url}", level="info")

            with trace.step("total scrape"):
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    context = await browser.new_context(
                        viewport={"width": 1440, "height": 1800},
                        locale="en-US",
                        user_agent=self.DEFAULT_USER_AGENT,
                        ignore_https_errors=True,
                        java_script_enabled=True,
                        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                    )
                    page = await context.new_page()

                    try:
                        await self._goto(page, product_url)

                        with self._trace.step("discovering review entry point"):
                            await self._wait_for_reviews_entry_point(page)

                        with self._trace.step("reviews modal open flow"):
                            await self._open_reviews_modal(
                                page,
                                product_url,
                                collected_reviews,
                            )

                        if self.consider_other_tabs:
                            review_tabs = await self._discover_review_tabs(page)
                            if not review_tabs:
                                review_tabs = ["United States"]

                            self._trace.message(
                                "review tabs: " + ", ".join(review_tabs),
                                level="info",
                            )
                        else:
                            self._trace.message(
                                "tab discovery skipped; using United States only",
                                level="info",
                            )
                            review_tabs = ["United States"]

                        for index, tab_name in enumerate(review_tabs):
                            if index > 0 and not await self._switch_review_tab(
                                page, tab_name
                            ):
                                continue

                            with self._trace.step(f"scraping reviews tab: {tab_name}"):
                                await self._scrape_active_modal_tab(
                                    page,
                                    product_url,
                                    collected_reviews,
                                    tab_name,
                                )
                            scraped_tabs.append(tab_name)
                        html = await page.content()
                        self._trace.message(
                            f"review scrape complete: {len(collected_reviews)} reviews captured",
                            level="info",
                        )
                    finally:
                        await context.close()
                        await browser.close()

        if not html:
            return ReviewScrapeResult(
                product_url=product_url,
                review_page_url=product_url,
                reviews_count=None,
                metadata=ReviewScrapeMetadata(
                    domain_metadata=ReviewScrapeDomainMetadata(),
                ),
            )

        return ReviewScrapeResult(
            product_url=product_url,
            review_page_url=product_url,
            reviews_count=len(collected_reviews),
            reviews=collected_reviews,
            metadata=ReviewScrapeMetadata(
                domain_metadata=ReviewScrapeDomainMetadata(
                    review_tabs=self._dedupe_strings(scraped_tabs)
                ),
            ),
        )

    async def _goto(self, page, product_url: str) -> None:
        with self._trace.step("opening product page in browser"):
            try:
                await page.goto(
                    product_url,
                    wait_until="commit",
                    timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
                )
            except Exception as e:
                self._trace.message(f"navigation failed: {e}", level="error")
                self._trace.message(
                    "commit navigation failed; retrying page load via domcontentloaded",
                    level="warn",
                )
                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
                )

    async def _wait_for_reviews_entry_point(self, page) -> None:
        with self._trace.step("checking for review entry point in page shell"):
            try:
                await page.wait_for_selector(
                    ", ".join(self.REVIEW_ENTRY_SELECTORS),
                    timeout=5_000,
                )
            except PlaywrightTimeoutError:
                self._trace.message(
                    "review entry point not found quickly; continuing",
                    level="warn",
                )

    async def _expand_all_reviews(
        self,
        page,
    ) -> None:
        for click_index in range(self.DEFAULT_MAX_LOAD_MORE_CLICKS):
            with self._trace.step(f"load-more iteration {click_index + 1}"):
                await self._nudge_reviews_panel(page)
                button, selector = await self._find_load_more_button(page)
                if button is None:
                    self._trace.message(
                        "🛑 no load more button found; stopping pagination",
                        level="warn",
                    )
                    break

                try:
                    await button.scroll_into_view_if_needed(timeout=5_000)
                except Exception as e:
                    self._trace.message(f"scroll into view failed: {e}", level="error")

                try:
                    self._trace.callout("selector", selector)
                    self._trace.message("clicking load more button", level="info")
                    await button.click(timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS)
                except Exception as e:
                    self._trace.message(
                        "load-more click failed; stopping", level="warn"
                    )
                    self._trace.message(f"click failed: {e}", level="error")
                    break

                try:
                    self._trace.message(
                        "wait for modal to settle after pagination",
                        level="info",
                    )
                    await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)
                except Exception as e:
                    self._trace.message(
                        "post-click settle failed; stopping", level="warn"
                    )
                    self._trace.message(f"settle wait failed: {e}", level="error")
                    break

    async def _scrape_active_modal_tab(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        tab_name: str,
    ) -> None:
        self._trace.message(f"capturing current tab state: {tab_name}", level="info")
        with self._trace.step(f"load-more pagination for {tab_name}"):
            await self._expand_all_reviews(page)
        self._trace.message(
            f"load-more pagination exhausted for {tab_name}", level="info"
        )
        with self._trace.step(f"extracting review cards for {tab_name}"):
            await self._capture_html_snapshot(
                page,
                product_url,
                collected_reviews,
                tab_name,
            )

    async def _discover_review_tabs(self, page) -> list[str]:
        selected_tabs: list[str] = []
        unselected_tabs: list[str] = []
        modal = page.locator(self.REVIEW_MODAL_TAB_SCOPE)
        if await modal.count() == 0:
            return []

        locator = modal.first.get_by_role("tab")
        count = await locator.count()

        for index in range(count):
            tab = locator.nth(index)
            try:
                if not await tab.is_visible():
                    continue
            except Exception as e:
                self._trace.message(f"tab visibility failed: {e}", level="warn")
                continue

            text = None
            try:
                text = await tab.text_content()
            except Exception:
                text = None

            if not text:
                try:
                    text = await tab.get_attribute("aria-label")
                except Exception:
                    text = None

            normalized = (text or "").strip()
            if not normalized:
                continue

            controls = None
            try:
                controls = await tab.get_attribute("aria-controls")
            except Exception:
                controls = None

            if not self._is_review_tab(normalized, controls):
                self._trace.message(f"tab skip: {normalized}", level="warn")
                continue

            self._trace.message(f"tab ok: {normalized}", level="info")
            is_active = False
            try:
                is_active = (await tab.get_attribute("aria-selected")) == "true"
            except Exception:
                is_active = False

            if is_active:
                selected_tabs.append(normalized)
            else:
                unselected_tabs.append(normalized)

        return self._dedupe_strings([*selected_tabs, *unselected_tabs])

    def _is_review_tab(
        self,
        tab_name: str,
        aria_controls: str | None,
    ) -> bool:
        normalized = tab_name.strip()
        if not normalized:
            return False

        if normalized not in self.REVIEW_REGION_TAB_ALLOWLIST:
            return False

        controls = (aria_controls or "").strip()
        return controls in self.REVIEW_TAB_CONTROLS

    async def _switch_review_tab(self, page, tab_name: str) -> bool:
        tab = page.get_by_role("tab", name=tab_name)
        if await tab.count() == 0:
            return False

        try:
            await tab.first.click(
                force=True, timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS
            )
            await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)
            return True
        except Exception as e:
            self._trace.message(f"tab switch failed: {e}", level="error")
            return False

    async def _open_reviews_modal(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
    ) -> None:
        """
        Open the IKEA reviews modal / expanded review view if a trigger is present.
        """
        with self._trace.step("pre-probe settle"):
            await page.wait_for_timeout(self.REVIEW_MODAL_OPEN_SETTLE_MS)

        for selector in self.REVIEW_MODAL_OPENERS:
            with self._trace.step("selector probe"):
                self._trace.callout("selector", selector)
                locator = page.locator(selector)
                count = await locator.count()
                if count == 0:
                    self._trace.message("no matches", level="warn")
                    continue

                try:
                    for index in range(count):
                        opener = locator.nth(index)
                        try:
                            if not await opener.is_visible():
                                continue
                            await opener.scroll_into_view_if_needed(timeout=5_000)
                            await opener.click(
                                timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS
                            )
                            await self._wait_for_review_ui_ready(page)
                            self._trace.message("matched visible opener", level="info")
                            return
                        except PlaywrightTimeoutError:
                            self._trace.message(
                                f"timed out waiting for review ui readiness after {self.REVIEW_UI_READY_TIMEOUT_MS}ms",
                                level="warn",
                            )
                            continue
                        except Exception as e:
                            self._trace.message(
                                f"selector click failed: {e}", level="error"
                            )
                            continue
                except Exception as e:
                    self._trace.message(f"selector probe failed: {e}", level="error")
                    continue

    async def _wait_for_review_ui_ready(self, page) -> None:
        for selector in self.REVIEW_MODAL_READY_SELECTORS:
            try:
                await page.locator(selector).first.wait_for(
                    state="visible",
                    timeout=self.REVIEW_UI_READY_TIMEOUT_MS,
                )
                return
            except PlaywrightTimeoutError:
                continue

        raise PlaywrightTimeoutError(
            f"timed out waiting for review ui readiness after {self.REVIEW_UI_READY_TIMEOUT_MS}ms"
        )

    async def _find_load_more_button(self, page):
        for selector in self.LOAD_MORE_SELECTORS:
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                continue

            for index in range(count):
                button = locator.nth(index)
                try:
                    if not await button.is_visible():
                        continue
                    if await button.is_disabled():
                        continue
                except Exception as e:
                    self._trace.message(
                        f"load-more control probe failed: {e}", level="error"
                    )
                    continue
                return button, selector

        return None, None

    async def _nudge_reviews_panel(self, page) -> None:
        """
        IKEA renders the reviews inside a scrollable modal content wrapper.
        Move that container to the bottom so the next page/load-more control is
        materialized in the same way a human would reach it.
        """
        content_wrapper = page.locator(".ugc-rr-pip-fe-theatre__content-wrapper")
        if await content_wrapper.count():
            try:
                await content_wrapper.first.evaluate(
                    "(el) => { el.scrollTop = el.scrollHeight; }"
                )
                await page.wait_for_timeout(500)
                return
            except Exception as e:
                self._trace.message(f"modal content scroll failed: {e}", level="error")

        for _ in range(3):
            try:
                await page.mouse.wheel(0, 1800)
            except Exception as e:
                self._trace.message(f"mouse wheel failed: {e}", level="error")
                break
            await page.wait_for_timeout(300)

    async def _capture_html_snapshot(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        stage: str,
    ) -> int:
        with self._trace.step(f"capturing HTML snapshot for {stage}"):
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            reviews = self._extract_reviews(soup, source_url=product_url)
            self._trace.message(
                f"parsed {len(reviews)} review candidates from DOM", level="info"
            )

            collected_reviews.extend(reviews)
            self._trace.message(
                f"{stage} snapshot: +{len(reviews)} reviews", level="info"
            )
            return len(reviews)

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        summary_node = soup.select_one(self.REVIEW_SUMMARY_SELECTOR)
        if summary_node:
            text = summary_node.get_text(" ", strip=True)
            return text or None

        page_text = soup.get_text(" ", strip=True)
        match = re.search(
            r"Review:\s*([0-9.]+)\s*out of 5 stars\.\s*Total reviews:\s*([0-9,]+)",
            page_text,
        )
        if match:
            rating, count = match.groups()
            return f"Review: {rating} out of 5 stars. Total reviews: {count}"

        return None

    def _extract_reviews(
        self, soup: BeautifulSoup, source_url: str | None
    ) -> list[Review]:
        reviews: list[Review] = []

        cards = self._review_cards(soup)
        for card in cards:
            title = self._extract_text(card, self.REVIEW_TITLE_SELECTOR)
            author = self._extract_text(card, self.REVIEW_AUTHOR_SELECTOR)
            body = self._extract_text(card, self.REVIEW_BODY_SELECTOR)
            rating = self._extract_rating(
                self._extract_text(card, self.REVIEW_RATING_SELECTOR)
                or self._extract_attr(card, self.REVIEW_RATING_SELECTOR, "aria-label")
            )

            if not any([title, author, body, rating]):
                continue

            reviews.append(
                Review(
                    author=author,
                    title=title,
                    body=body or "",
                    rating=rating,
                    source=ReviewSource.DOM,
                    source_url=source_url,
                )
            )

        return self._dedupe_reviews(reviews)

    def _review_cards(self, soup: BeautifulSoup):
        modal_cards = soup.select(
            ".ugc-rr-pip-fe-modal-wrapper--open .ugc-rr-pip-fe-tabs__panel:not([hidden]) .ugc-rr-pip-fe-review"
        )
        if modal_cards:
            return modal_cards

        cards = []
        for selector in self.REVIEW_CARD_SELECTORS:
            cards.extend(soup.select(selector))
        return cards

    def _extract_text(self, node, selector: str) -> str | None:
        child = node.select_one(selector)
        if not child:
            return None
        text = child.get_text(" ", strip=True)
        return text or None

    def _extract_attr(self, node, selector: str, attribute: str) -> str | None:
        child = node.select_one(selector)
        if not child:
            return None
        value = child.get(attribute)
        if value is None:
            return None
        return str(value).strip() or None

    def _extract_rating(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.strip())
        except ValueError:
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value)
            return float(match.group(1)) if match else None

    def _dedupe_reviews(self, reviews: list[Review]) -> list[Review]:
        deduped: list[Review] = []
        seen: set[tuple[str, str, str]] = set()

        for review in reviews:
            key = (
                self._normalize(review.title),
                self._normalize(review.author),
                self._normalize(review.body),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(review)

        return deduped

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()

        for value in values:
            normalized = self._normalize(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(value)

        return deduped

    def _normalize(self, value: str | None) -> str:
        return re.sub(r"\s+", " ", value or "").strip().lower()

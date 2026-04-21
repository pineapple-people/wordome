import re
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

from bs4 import BeautifulSoup
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from rich.console import Console
from rich.text import Text

from wordome.domain.reviews.models import (
    Review,
    ReviewScrapeDomainMetadata,
    ReviewScrapeMetadata,
    ReviewScrapeResult,
    ReviewSource,
)


class _RichTraceLogger:
    """
    Lightweight rich-backed tracer that renders nested steps as a tree.
    """

    def __init__(self, scope: str):
        self.scope = scope
        self.console = Console(stderr=True, highlight=False, soft_wrap=True)
        self._depth = 0

    def _indent(self, depth: int | None = None) -> str:
        depth = self._depth if depth is None else depth
        if depth <= 0:
            return ""
        return "│   " * (depth - 1) + "├── "

    def _render(self, message: str, style: str, depth: int | None = None) -> None:
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
        text.append(message, style=style)
        self.console.print(text)

    def _render_callout(
        self,
        label: str,
        value: str,
        depth: int | None = None,
        label_style: str = "bold cyan",
        value_style: str = "bold #a855f7",
    ) -> None:
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
        text.append(label, style=label_style)
        text.append(": ", style="dim")
        text.append(value, style=value_style)
        self.console.print(text)

    def _render_status(
        self,
        label: str,
        status: str,
        status_style: str,
        depth: int | None = None,
        detail_label: str | None = None,
        detail_value: str | None = None,
        detail_label_style: str = "bold #ff8ad6",
        detail_value_style: str = "bold #ff8ad6",
    ) -> None:
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
        text.append(label, style="bold cyan")
        text.append("  ", style="dim")
        text.append(f"[{status}]", style=status_style)
        if detail_label and detail_value:
            text.append("  ", style="dim")
            text.append(f"[{detail_label}", style=detail_label_style)
            text.append(" ", style="dim")
            text.append(detail_value, style=detail_value_style)
            text.append("]", style=detail_label_style)
        self.console.print(text)

    def log(self, message: str) -> None:
        self._render(message, "white")

    def info(self, message: str) -> None:
        self._render(message, "cyan")

    def warn(self, message: str) -> None:
        self._render(message, "yellow")

    def error(self, message: str) -> None:
        self._render(message, "bold red")

    def callout(
        self,
        label: str,
        value: str,
        depth: int | None = None,
        label_style: str = "bold cyan",
        value_style: str = "bold magenta",
    ) -> None:
        self._render_callout(
            label,
            value,
            depth=depth,
            label_style=label_style,
            value_style=value_style,
        )

    @contextmanager
    def step(self, label: str):
        start = perf_counter()
        depth = self._depth
        self._render(label, "bold cyan", depth=depth)
        self._depth += 1
        try:
            yield
        except Exception as exc:
            elapsed = perf_counter() - start
            self._depth -= 1
            self._render_status(
                label,
                "failed",
                "bold red",
                depth=depth,
                detail_label="after",
                detail_value=f"{elapsed:.2f}s: {exc}",
                detail_value_style="bold red",
            )
            raise
        else:
            elapsed = perf_counter() - start
            self._depth -= 1
            self._render_status(
                label,
                "done",
                "green",
                depth=depth,
                detail_label="runtime:",
                detail_value=f"{elapsed:.2f}s",
                detail_value_style="bold green",
            )


_TRACE_CONTEXT: ContextVar[_RichTraceLogger | None] = ContextVar(
    "reviews_scraper_ikea_trace",
    default=None,
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
    DEFAULT_MODAL_SETTLE_MS = 250
    REVIEW_MODAL_PAGINATION_TIMEOUT_MS = 5_000
    DEFAULT_MAX_LOAD_MORE_CLICKS = 20

    # Feature toggles.
    INCLUDE_OTHER_COUNTRIES = False

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
    LOAD_MORE_SELECTORS = (
        "button:has-text('Load more')",
        "button:has-text('Load More')",
        "button:has-text('More reviews')",
        "div.ugc-rr-pip-fe-reviews__load-more button",
        ".ugc-rr-pip-fe-btn.ugc-rr-pip-fe-btn--small.ugc-rr-pip-fe-btn--secondary.ugc-rr-pip-fe-reviews__load-more__button",
        "button.ugc-rr-pip-fe-reviews__load-more__button",
    )
    REVIEW_MODAL_OPENERS = (
        "div.js-ugc-container.pipf-ratings-and-qna > button.pipf-rating",
        "div.js-ugc-container.pipf-ratings-and-qna .pipf-rating",
        "div.js-ugc-container.pipf-ratings-and-qna button.pipf-rating",
        ".pipf-rating",
        "button:has-text('Show all reviews')",
        "button:has-text('Show reviews')",
        "button:has-text('Reviews')",
    )
    REVIEW_ENTRY_SELECTORS = (
        *REVIEW_MODAL_OPENERS,
        ".pipf-seo-reviews__summary",
        "[class*='review']",
    )
    REVIEW_TABS = ("United States", "Other countries")
    # REVIEW_API_MARKER = "web-api.ikea.com/tugc/public/v5/reviews/"
    REVIEW_MODAL_PAGINATION_SELECTOR = "div.ugc-rr-pip-fe-reviews__load-more"

    def __init__(self) -> None:
        self._default_trace = _RichTraceLogger(self.__class__.__name__)

    @property
    def _trace(self) -> _RichTraceLogger:
        return _TRACE_CONTEXT.get() or self._default_trace

    def _log(self, message: str) -> None:
        self._trace.log(message)

    async def scrape(self, product_url: str) -> ReviewScrapeResult:
        trace = _RichTraceLogger(self.__class__.__name__)
        token = _TRACE_CONTEXT.set(trace)
        trace.info(f"scraping product page: {product_url}")
        html: str | None = None
        collected_reviews: list[Review] = []
        scraped_tabs: list[str] = []

        try:
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

                        with self._trace.step("scraping reviews tab: United States"):
                            await self._scrape_active_modal_tab(
                                page,
                                product_url,
                                collected_reviews,
                                "United States",
                            )
                        scraped_tabs.append("United States")
                        self._trace.info(
                            f"reviews tab complete: United States; reviews captured so far: {len(collected_reviews)}"
                        )
                        if self.INCLUDE_OTHER_COUNTRIES:
                            # Optional: also scrape the regional "Other countries" tab.
                            additional_tabs = self.REVIEW_TABS[1:]
                            for tab_name in additional_tabs:
                                if await self._switch_review_tab(page, tab_name):
                                    self._trace.info(f"scraping tab: {tab_name}")
                                    await self._scrape_active_modal_tab(
                                        page,
                                        product_url,
                                        collected_reviews,
                                        tab_name,
                                    )
                                    scraped_tabs.append(tab_name)
                        html = await page.content()
                    finally:
                        await context.close()
                        await browser.close()
        finally:
            _TRACE_CONTEXT.reset(token)

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
                self._trace.error(f"navigation failed: {e}")
                self._trace.warn(
                    "commit navigation failed; retrying page load via domcontentloaded"
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
                self._trace.warn("review entry point not found quickly; continuing")

    async def _expand_all_reviews(
        self,
        page,
    ) -> None:
        for click_index in range(self.DEFAULT_MAX_LOAD_MORE_CLICKS):
            self._trace.info(f"load-more iteration {click_index + 1}")
            await self._nudge_reviews_panel(page)
            button = await self._find_load_more_button(page)
            if button is None:
                self._trace.warn("no load more button found; stopping pagination")
                break

            try:
                await button.scroll_into_view_if_needed(timeout=5_000)
            except Exception as e:
                self._trace.error(f"scroll into view failed: {e}")

            try:
                self._trace.info("click load more")
                await button.click(timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS)
            except Exception as e:
                self._trace.warn("load-more click failed; stopping")
                self._trace.error(f"click failed: {e}")
                break

            try:
                self._trace.info("wait for modal to settle after pagination")
                await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)
            except Exception as e:
                self._trace.warn("post-click settle failed; stopping")
                self._trace.error(f"settle wait failed: {e}")
                break

    async def _scrape_active_modal_tab(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        tab_name: str,
    ) -> None:
        self._trace.info(f"capturing current tab state: {tab_name}")
        with self._trace.step(f"load-more pagination for {tab_name}"):
            await self._expand_all_reviews(page)
        self._trace.info(f"load-more pagination exhausted for {tab_name}")
        with self._trace.step(f"extracting review cards for {tab_name}"):
            await self._capture_html_snapshot(
                page,
                product_url,
                collected_reviews,
                f"{tab_name} capture HTML snapshot",
            )

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
            self._trace.error(f"tab switch failed: {e}")
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
        for selector in self.REVIEW_MODAL_OPENERS:
            with self._trace.step("selector probe"):
                self._trace.callout("selector", selector)
                locator = page.locator(selector)
                count = await locator.count()
                if count == 0:
                    self._trace.warn("no matches")
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
                            await self._wait_for_reviews_modal_ready(page)
                            self._trace.info("matched visible opener")
                            return
                        except PlaywrightTimeoutError:
                            self._trace.warn("timed out waiting for modal readiness")
                            continue
                        except Exception as e:
                            self._trace.error(f"selector click failed: {e}")
                            continue
                except Exception as e:
                    self._trace.error(f"selector probe failed: {e}")
                    continue

    async def _wait_for_reviews_modal_ready(self, page) -> None:
        await page.wait_for_selector(
            self.REVIEW_MODAL_PAGINATION_SELECTOR,
            state="visible",
            timeout=self.REVIEW_MODAL_PAGINATION_TIMEOUT_MS,
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
                    self._trace.error(f"load-more control probe failed: {e}")
                    continue
                return button

        return None

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
                self._trace.error(f"modal content scroll failed: {e}")

        for _ in range(3):
            try:
                await page.mouse.wheel(0, 1800)
            except Exception as e:
                self._trace.error(f"mouse wheel failed: {e}")
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
            self._trace.info(f"parsed {len(reviews)} review candidates from DOM")

            collected_reviews.extend(reviews)
            self._trace.info(f"{stage}: added {len(reviews)} reviews")
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

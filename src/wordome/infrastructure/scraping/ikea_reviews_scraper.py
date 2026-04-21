import re

from bs4 import BeautifulSoup
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from wordome.domain.review_models import (
    Review,
    ReviewScrapeMetadata,
    ReviewScrapeResult,
    ReviewSource,
)


class IkeaReviewsScraper:
    """
    POC scraper for IKEA PDP review collection.

    The page exposes review cards in the DOM and a dedicated "Load more" button
    in the review modal / section. We treat each click as a pagination step:
    capture the current visible batch, wait for the batch to change, and then
    capture the next page of reviews.
    """

    DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000
    DEFAULT_WAIT_MS = 750
    DEFAULT_MODAL_SETTLE_MS = 500
    DEFAULT_MAX_LOAD_MORE_CLICKS = 50
    INCLUDE_OTHER_COUNTRIES = False
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    REVIEW_CARD_SELECTORS = (
        ".ugc-rr-pip-fe-review",
        ".pipf-seo-reviews__review",
        "[class*='ugc-rr-pip-fe-reviews__review']",
    )
    LOAD_MORE_SELECTORS = (
        "button:has-text('Load more')",
        "button:has-text('Load More')",
        "button:has-text('More reviews')",
        "div.ugc-rr-pip-fe-reviews__load-more button",
        ".ugc-rr-pip-fe-btn.ugc-rr-pip-fe-btn--small.ugc-rr-pip-fe-btn--secondary.ugc-rr-pip-fe-reviews__load-more__button",
        "button.ugc-rr-pip-fe-reviews__load-more__button",
    )
    REVIEW_TITLE_SELECTOR = ".ugc-rr-pip-fe-review__title, .pipf-seo-reviews__review-title, [class*='review-title']"
    REVIEW_AUTHOR_SELECTOR = ".ugc-rr-pip-fe-reviewer-name, .pipf-seo-reviews__review-name, [class*='review-name']"
    REVIEW_BODY_SELECTOR = ".ugc-rr-pip-fe-review__text, .pipf-seo-reviews__review-text, [class*='review-text']"
    REVIEW_RATING_SELECTOR = ".ugc-rr-pip-fe-rating__stars, .pipf-seo-reviews__review-ratingValue, [class*='review-ratingValue']"
    REVIEW_SUMMARY_SELECTOR = ".pipf-rating__sr-only"
    REVIEW_MODAL_OPENERS = (
        "button:has-text('Show all reviews')",
        "button:has-text('Show reviews')",
        "button:has-text('Reviews')",
        ".pipf-rating",
    )
    REVIEW_TABS = ("United States", "Other countries")
    REVIEW_API_MARKER = "web-api.ikea.com/tugc/public/v5/reviews/"

    async def scrape(self, product_url: str) -> ReviewScrapeResult:
        captured_notes: list[str] = []
        captured_review_api_urls: list[str] = []
        html: str | None = None
        collected_reviews: list[Review] = []
        seen_review_keys: set[tuple[str, str, str, str]] = set()

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

            def on_request(request):
                url = request.url
                if self.REVIEW_API_MARKER in url.lower():
                    captured_review_api_urls.append(url)

            try:
                page.on("request", on_request)
                await self._goto(page, product_url)
                await self._wait_for_reviews_shell(page)
                await self._open_reviews_modal(
                    page,
                    product_url,
                    collected_reviews,
                    seen_review_keys,
                    captured_notes,
                )
                await self._scrape_active_modal_tab(
                    page,
                    product_url,
                    collected_reviews,
                    seen_review_keys,
                    captured_notes,
                    "United States",
                )
                if self.INCLUDE_OTHER_COUNTRIES:
                    # Toggle this on when you want to merge the regional tab too.
                    for tab_name in self.REVIEW_TABS[1:]:
                        if await self._switch_review_tab(page, tab_name):
                            await self._scrape_active_modal_tab(
                                page,
                                product_url,
                                collected_reviews,
                                seen_review_keys,
                                captured_notes,
                                tab_name,
                            )
                html = await page.content()
            finally:
                await context.close()
                await browser.close()

        if not html:
            return ReviewScrapeResult(
                product_url=product_url,
                review_page_url=product_url,
                reviews_count=None,
                metadata=ReviewScrapeMetadata(
                    notes=["Failed to fetch IKEA PDP HTML."],
                ),
            )

        soup = BeautifulSoup(html, "html.parser")
        summary = self._extract_summary(soup)
        reviews_count = self._extract_reviews_count(soup)
        notes: list[str] = []
        if summary:
            notes.append(summary)
        if captured_review_api_urls:
            notes.append(
                f"Observed IKEA review API calls: {len(captured_review_api_urls)}"
            )
        notes.extend(captured_notes)
        if not collected_reviews:
            notes.append("No IKEA review cards were extracted from the HTML.")

        return ReviewScrapeResult(
            product_url=product_url,
            review_page_url=product_url,
            reviews_count=reviews_count if reviews_count is not None else len(collected_reviews),
            reviews=collected_reviews,
            metadata=ReviewScrapeMetadata(
                captured_review_api_urls=self._dedupe_strings(captured_review_api_urls),
                notes=notes,
            ),
        )

    async def _goto(self, page, product_url: str) -> None:
        try:
            await page.goto(
                product_url,
                wait_until="commit",
                timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
            )
        except Exception:
            await page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
            )

    async def _wait_for_reviews_shell(self, page) -> None:
        try:
            await page.wait_for_selector(
                ", ".join(self.REVIEW_CARD_SELECTORS + self.LOAD_MORE_SELECTORS),
                timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)

    async def _expand_all_reviews(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        seen_review_keys: set[tuple[str, str, str, str]],
        notes: list[str],
    ) -> None:
        for _ in range(self.DEFAULT_MAX_LOAD_MORE_CLICKS):
            await self._nudge_reviews_panel(page)
            button = await self._find_load_more_button(page)
            if button is None:
                break

            try:
                await button.scroll_into_view_if_needed(timeout=5_000)
            except Exception:
                pass

            try:
                async with page.expect_response(
                    lambda response: self.REVIEW_API_MARKER in response.url.lower(),
                    timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
                ):
                    await button.click(timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS)
            except Exception as exc:
                notes.append(f"Stopped at load-more click failure: {exc}")
                break

            try:
                await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)
                new_reviews = await self._harvest_current_reviews(
                    page,
                    product_url,
                    collected_reviews,
                    seen_review_keys,
                    notes,
                    "pagination",
                )
            except Exception as exc:
                notes.append(f"Stopped while waiting for additional reviews: {exc}")
                break

            if new_reviews == 0:
                notes.append(
                    "Load more exhausted: the next review page produced no new cards."
                )
                break

    async def _scrape_active_modal_tab(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        seen_review_keys: set[tuple[str, str, str, str]],
        notes: list[str],
        tab_name: str,
    ) -> None:
        notes.append(f"Scraping IKEA review tab: {tab_name}")
        await self._harvest_current_reviews(
            page,
            product_url,
            collected_reviews,
            seen_review_keys,
            notes,
            f"{tab_name} initial",
        )
        await self._expand_all_reviews(
            page,
            product_url,
            collected_reviews,
            seen_review_keys,
            notes,
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
        except Exception:
            return False

    async def _open_reviews_modal(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        seen_review_keys: set[tuple[str, str, str, str]],
        notes: list[str],
    ) -> None:
        """
        Open the IKEA reviews modal / expanded review view if a trigger is present.
        """
        for selector in self.REVIEW_MODAL_OPENERS:
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                continue

            for index in range(count):
                opener = locator.nth(index)
                try:
                    if not await opener.is_visible():
                        continue
                    await opener.scroll_into_view_if_needed(timeout=5_000)
                    await opener.click(timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS)
                    await page.wait_for_selector(
                        "div.ugc-rr-pip-fe-reviews__load-more",
                        timeout=self.DEFAULT_NAVIGATION_TIMEOUT_MS,
                    )
                    await page.wait_for_timeout(self.DEFAULT_MODAL_SETTLE_MS)
                    notes.append(f"Opened reviews modal via: {selector}")
                    return
                except Exception:
                    continue

        notes.append("No explicit reviews modal opener was found.")

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
                except Exception:
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
            except Exception:
                pass

        for _ in range(3):
            try:
                await page.mouse.wheel(0, 1800)
            except Exception:
                break
            await page.wait_for_timeout(300)

    async def _review_card_count(self, page) -> int:
        selectors = ", ".join(self.REVIEW_CARD_SELECTORS)
        return await page.locator(selectors).count()

    async def _harvest_current_reviews(
        self,
        page,
        product_url: str,
        collected_reviews: list[Review],
        seen_review_keys: set[tuple[str, str, str, str]],
        notes: list[str],
        stage: str,
    ) -> int:
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        reviews = self._extract_reviews(soup, source_url=product_url)

        new_reviews = 0
        for review in reviews:
            key = self._review_key(review)
            if key in seen_review_keys:
                continue
            seen_review_keys.add(key)
            collected_reviews.append(review)
            new_reviews += 1

        notes.append(f"Captured {new_reviews} new reviews during {stage} snapshot.")
        return new_reviews

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

    def _extract_reviews_count(self, soup: BeautifulSoup) -> int | None:
        summary_node = soup.select_one(self.REVIEW_SUMMARY_SELECTOR)
        text = summary_node.get_text(" ", strip=True) if summary_node else ""
        if not text:
            text = soup.get_text(" ", strip=True)

        match = re.search(r"Total reviews:\s*([0-9,]+)", text)
        if not match:
            return None

        return int(match.group(1).replace(",", ""))

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

    def _review_key(self, review: Review) -> tuple[str, str, str, str]:
        return (
            self._normalize(review.title),
            self._normalize(review.author),
            self._normalize(review.body),
            str(review.rating or ""),
        )

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

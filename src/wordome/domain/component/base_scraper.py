import trafilatura

from .word_stats_extractor import WordStatsExtractor


class BaseScraper:
    def __init__(self, use_auto_extract: bool = True):
        self.extractor = WordStatsExtractor()
        self.use_auto_extract = use_auto_extract

    def extract_reviews_list(self, html: str, selector: str | None = None) -> list[str]:
        """
        Return a list with all the reviews
        """
        if not html:
            return []

        if selector:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            elements = soup.select(selector)
            return [el.get_text(separator=" ", strip=True) for el in elements]

        if self.use_auto_extract:
            content = trafilatura.extract(html, include_comments=True)
            return content.split("\n") if content else []

    def process_html_to_stats(self, html: str, selector: str | None = None) -> list:
        reviews = self.extract_reviews_list(html, selector)

        if not reviews:
            print("Warning: No reviews found!")
            return []

        print(f"\n---- Found {len(reviews)} reviews ---")
        for i, review in enumerate(reviews, 1):
            print(f"Review #{i}: {review[:100]}...")
        print("-------------------------\n")

        combined_text = " ".join(reviews)
        return self.extractor.process(combined_text)

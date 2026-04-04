from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ReviewDetectionResult:
    has_reviews: bool
    confidence: str
    score: int
    matched_keywords: list[str]


class ReviewSectionDetector:
    """
    Simple detector to check if HTML has a user review section.
    """

    # Simple list of words that suggest reviews
    REVIEW_KEYWORDS = [
        "review",
        "rating",
        "stars",
        "reviewer",
        "/5",
        "out of 5",
        "recommend",
        "helpful",
        "verified purchase",
        "customer review",
    ]

    def process(self, html_content: str) -> ReviewDetectionResult:
        """
        Detect if HTML contains a review section
        """
        # 1. Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 2. Get all text
        page_text = soup.get_text(" ", strip=True).lower()

        # 3. Count review keywords
        matched_words = []
        for keyword in self.REVIEW_KEYWORDS:
            if keyword in page_text:
                matched_words.append(keyword)

        score = len(matched_words)

        # 4. Determine result
        has_reviews = score >= 3  # At least 3 review-related words
        confidence = self._get_confidence(score)

        return ReviewDetectionResult(
            has_reviews=has_reviews,
            confidence=confidence,
            score=score,
            matched_keywords=matched_words,
        )

    def _get_confidence(self, score: int) -> str:
        if score >= 5:
            return "high"
        elif score >= 3:
            return "medium"
        else:
            return "low"

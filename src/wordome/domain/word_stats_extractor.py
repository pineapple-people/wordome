import re
from collections import Counter
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class WordStats:
    """
    A pure Data Transfer Object (DTO).
    Represents the statistical result for a single word.
    """

    word: str
    count: int
    frequency: float


class WordStatsExtractor:
    """
    Extracts top N most frequent words from HTML content with frequency statistics
    Note: example to demonstrate basic functionality with BeautifulSoup
    """

    DEFAULT_TOP_N = 10
    DEFAULT_MIN_WORD_LENGTH = 3
    DEFAULT_IGNORE_WORDS = []

    """
    Responsible for extracting numerical insights from raw text
    Extracts content from HTML
    """

    def process(self, html_content: str) -> list[WordStats]:
        """
        1. Clean (Extract words)
        2. Analyze (Count & Frequency)
        3. Package (Create WordStats)
        """

        # 1. Convert to soup object
        soup = BeautifulSoup(html_content, "html.parser")

        # 2. Strip HTML tags
        raw_text = soup.get_text(separator=" ")

        # 3. Tokenize (Clean non-alphanumeric and lowercase)
        words = re.findall(r"\b\w+\b", raw_text.lower())

        # 4. Filter by length and stop words
        filtered_words: list[str] = [
            w
            for w in words
            if len(w) >= WordStatsExtractor.DEFAULT_MIN_WORD_LENGTH
            and w not in WordStatsExtractor.DEFAULT_IGNORE_WORDS
        ]

        # 5. Calculate Frequencies
        total_count: int = len(filtered_words)
        counts: list[tuple[str, int]] = Counter(filtered_words).most_common(
            self.DEFAULT_TOP_N
        )

        # 6. Map to dataclass (generator expression, then return a reusable list)
        stats_generator = (
            WordStats(
                word=word,
                count=count,
                frequency=round(count / total_count, 4) if total_count > 0 else 0.0,
            )
            for word, count in counts
        )
        return list(stats_generator)

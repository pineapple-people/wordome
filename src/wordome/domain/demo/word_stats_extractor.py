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
    Extracts top N most frequent words from HTML content with frequency statistics.
    """

    DEFAULT_TOP_N = 10
    DEFAULT_MIN_WORD_LENGTH = 3
    DEFAULT_IGNORE_WORDS = []

    def process(self, html_content: str) -> list[WordStats]:
        soup = BeautifulSoup(html_content, "html.parser")
        raw_text = soup.get_text(separator=" ")
        words = re.findall(r"\b\w+\b", raw_text.lower())

        filtered_words: list[str] = [
            w
            for w in words
            if len(w) >= WordStatsExtractor.DEFAULT_MIN_WORD_LENGTH
            and w not in WordStatsExtractor.DEFAULT_IGNORE_WORDS
        ]

        total_count: int = len(filtered_words)
        counts: list[tuple[str, int]] = Counter(filtered_words).most_common(
            self.DEFAULT_TOP_N
        )

        stats_generator = (
            WordStats(
                word=word,
                count=count,
                frequency=round(count / total_count, 4) if total_count > 0 else 0.0,
            )
            for word, count in counts
        )
        return list(stats_generator)

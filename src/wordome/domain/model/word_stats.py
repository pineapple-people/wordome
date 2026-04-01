from dataclasses import dataclass


@dataclass(frozen=True)
class WordStats:
    """
    A pure Data Transfer Object (DTO).
    Represents the statistical result for a single word.
    """

    word: str
    count: int
    frequency: float

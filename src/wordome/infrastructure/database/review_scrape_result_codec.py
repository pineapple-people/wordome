import json
from hashlib import sha256
from typing import Any

from wordome.domain.reviews.models import (
    Review,
    ReviewScrapeDomainMetadata,
    ReviewScrapeMetadata,
    ReviewScrapeResult,
    ReviewSource,
)
from wordome.infrastructure.database.review_scrape_orm import ReviewScrapeRecord


class ReviewScrapeResultCodec:
    """Translate ORM persistence records to and from review domain DTOs."""

    @staticmethod
    def _serialize_metadata(metadata: ReviewScrapeMetadata) -> dict[str, Any]:
        return {
            "domain_metadata": {
                "review_tabs": metadata.domain_metadata.review_tabs,
            }
        }

    @staticmethod
    def _serialize_reviews(reviews: list[Review]) -> list[dict[str, Any]]:
        return [
            {
                "author": review.author,
                "title": review.title,
                "body": review.body,
                "rating": review.rating,
                "rating_scale_max": review.rating_scale_max,
                "date": review.date,
                "source": review.source.value if review.source else None,
                "source_url": review.source_url,
            }
            for review in reviews
        ]

    @staticmethod
    def compute_snapshot_hash(
        *,
        product_url: str,
        review_page_url: str | None,
        reviews_count: int | None,
        metadata_payload: dict[str, Any],
        reviews_payload: list[dict[str, Any]],
    ) -> str:
        payload = {
            "product_url": product_url,
            "review_page_url": review_page_url,
            "reviews_count": reviews_count,
            "metadata": metadata_payload,
            "reviews": reviews_payload,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def to_record(result: ReviewScrapeResult) -> ReviewScrapeRecord:
        metadata_payload = ReviewScrapeResultCodec._serialize_metadata(result.metadata)
        reviews_payload = ReviewScrapeResultCodec._serialize_reviews(result.reviews)
        return ReviewScrapeRecord(
            product_url=result.product_url,
            review_page_url=result.review_page_url,
            reviews_count=result.reviews_count,
            source_name="reviews_scraper_ikea",
            pipeline_version="v1",
            snapshot_hash=ReviewScrapeResultCodec.compute_snapshot_hash(
                product_url=result.product_url,
                review_page_url=result.review_page_url,
                reviews_count=result.reviews_count,
                metadata_payload=metadata_payload,
                reviews_payload=reviews_payload,
            ),
            metadata_payload=metadata_payload,
            reviews_payload=reviews_payload,
        )

    @classmethod
    def from_record(cls, record: ReviewScrapeRecord) -> ReviewScrapeResult:
        metadata_payload = cls._ensure_dict(record.metadata_payload)
        domain_metadata = metadata_payload.get("domain_metadata", {})
        return ReviewScrapeResult(
            product_url=record.product_url,
            review_page_url=record.review_page_url,
            reviews_count=record.reviews_count,
            reviews=cls._deserialize_reviews(record.reviews_payload),
            metadata=ReviewScrapeMetadata(
                domain_metadata=ReviewScrapeDomainMetadata(
                    review_tabs=list(domain_metadata.get("review_tabs", []))
                )
            ),
        )

    @staticmethod
    def _deserialize_reviews(reviews_json: Any) -> list[Review]:
        reviews_payload = ReviewScrapeResultCodec._ensure_list(reviews_json)
        reviews: list[Review] = []
        for item in reviews_payload:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            reviews.append(
                Review(
                    author=item.get("author"),
                    title=item.get("title"),
                    body=item.get("body") or "",
                    rating=item.get("rating"),
                    rating_scale_max=item.get("rating_scale_max"),
                    date=item.get("date"),
                    source=ReviewSource(source) if source else None,
                    source_url=item.get("source_url"),
                )
            )
        return reviews

    @staticmethod
    def _ensure_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        return {}

    @staticmethod
    def _ensure_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else []
        return []

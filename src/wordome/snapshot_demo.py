import asyncio
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from wordome.domain.reviews.models import (
    Review,
    ReviewScrapeDomainMetadata,
    ReviewScrapeMetadata,
    ReviewScrapeResult,
    ReviewSource,
)
from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection
from wordome.infrastructure.database.snowflake_repository import SnowflakeRepository


def _build_snapshot(product_url: str, body: str, rating: float) -> ReviewScrapeResult:
    return ReviewScrapeResult(
        product_url=product_url,
        review_page_url=f"{product_url}#reviews",
        reviews_count=1,
        reviews=[
            Review(
                author="Codex",
                title="Snapshot demo",
                body=body,
                rating=rating,
                rating_scale_max=5,
                date="2026-04-24",
                source=ReviewSource.API,
                source_url=f"{product_url}#source",
            )
        ],
        metadata=ReviewScrapeMetadata(
            domain_metadata=ReviewScrapeDomainMetadata(review_tabs=["United States"])
        ),
    )


async def run_snapshot_demo_async() -> None:
    db_path = Path(tempfile.gettempdir()) / "wordome_snapshot_demo.sqlite3"
    if db_path.exists():
        db_path.unlink()

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    repository = SnowflakeRepository(connection=SnowflakeConnection(engine=engine))
    product_url = "https://example.com/products/sofa"

    first_snapshot_event_id = await repository.append_scrape_snapshot(
        _build_snapshot(product_url, "First crawl body", 4.0)
    )
    second_snapshot_event_id = await repository.append_scrape_snapshot(
        _build_snapshot(product_url, "Second crawl body", 5.0)
    )

    latest_snapshot = await repository.get_latest_snapshot(product_url)
    snapshots = await repository.list_snapshots(product_url, limit=10)

    print(f"database={db_path}")
    print(f"first_snapshot_event_id={first_snapshot_event_id}")
    print(f"second_snapshot_event_id={second_snapshot_event_id}")
    print(f"snapshot_count={len(snapshots)}")
    print(
        f"latest_review_body={latest_snapshot.reviews[0].body if latest_snapshot else ''}"
    )
    print(
        f"latest_rating={latest_snapshot.reviews[0].rating if latest_snapshot else ''}"
    )


def run_snapshot_demo() -> None:
    asyncio.run(run_snapshot_demo_async())


if __name__ == "__main__":
    run_snapshot_demo()

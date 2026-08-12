"""Scheduler contract. Production wiring: managed cron -> these idempotent jobs -> Postgres."""
from datetime import datetime, timezone
from app.domain.recommendation import rank_candidates
from app.providers.mock import MOCK_CANDIDATES, MOCK_REGIME


async def ingest_market_snapshot(as_of: datetime | None = None) -> dict:
    return {"job": "market_snapshot", "as_of": as_of or datetime.now(timezone.utc), "status": "provider_pending"}


async def ingest_news_feed(as_of: datetime | None = None) -> dict:
    return {"job": "news_feed", "as_of": as_of or datetime.now(timezone.utc), "status": "source_registry_pending"}


async def build_daily_recommendations(as_of: datetime | None = None) -> dict:
    return {"job": "daily_recommendations", "as_of": as_of or datetime.now(timezone.utc), "rows": rank_candidates(MOCK_CANDIDATES, MOCK_REGIME, 5)}

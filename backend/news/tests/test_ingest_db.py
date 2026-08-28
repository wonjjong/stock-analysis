"""
DB 를 실제로 때리는 테스트.

여기 있는 이유: 기존 테스트는 전부 `crawler/` 의 순수 함수만 검사한다. 그래서
`insert_ignore` 가 컬럼을 하나 빠뜨려 **모든 수집이 NOT NULL 위반으로 실패하는**
버그가 96개를 전부 통과하고 살아남았다. 인서트 경로를 지나는 테스트가 하나도
없었기 때문이다.
"""

from datetime import UTC, datetime

import pytest

from news.models import InsightStatus, NewsArticle, NewsSource
from news.services.ingest import next_crawl_ms


@pytest.fixture
def source(db: None) -> NewsSource:
    now = datetime.now(tz=UTC)
    return NewsSource.objects.create(
        name="테스트", url="https://example.com/feed.xml", symbol="GENERAL",
        company="시장 전체", category="종합", crawl_hour_kst=6, max_pages=1,
        window_hours=36, is_active=True, last_status="대기",
        next_crawl_at=now, created_at=now, updated_at=now,
    )


def _values(source: NewsSource, url: str) -> dict:
    now = datetime.now(tz=UTC)
    return {
        "source_id": source.pk, "symbol": "GENERAL", "title": "제목",
        "canonical_url": url, "excerpt": "요약", "published_at": now,
        "content_hash": "hash-" + url, "sentiment": "중립", "sentiment_score": 50,
        "materiality": "낮음", "relevance": 100, "event_type": "산업·시장동향",
        "score_adjustment": 0, "analysis_summary": "요약", "collected_at": now,
        "insight_status": InsightStatus.PENDING,
    }


def test_insert_ignore_writes_a_row(source: NewsSource) -> None:
    """
    insight_status 는 모델에만 default 가 있고 DDL 에는 DEFAULT 가 없다. raw SQL 이
    ORM 을 우회하므로 컬럼 목록에서 빠지면 여기서 NOT NULL 위반이 난다.
    """
    inserted = NewsArticle.objects.insert_ignore(**_values(source, "https://example.com/a"))
    assert inserted == 1
    article = NewsArticle.objects.get(canonical_url="https://example.com/a")
    assert article.insight_status == InsightStatus.PENDING


def test_insert_ignore_dedupes_on_canonical_url(source: NewsSource) -> None:
    """겹치는 수집 창이 중복 행을 만들지 않는다는 계약. 주기를 줄이면 더 중요해진다."""
    values = _values(source, "https://example.com/dup")
    assert NewsArticle.objects.insert_ignore(**values) == 1
    assert NewsArticle.objects.insert_ignore(**values) == 0
    assert NewsArticle.objects.filter(canonical_url="https://example.com/dup").count() == 1


def test_insert_ignore_rejects_a_missing_column(source: NewsSource) -> None:
    values = _values(source, "https://example.com/b")
    del values["insight_status"]
    with pytest.raises(ValueError, match="insight_status"):
        NewsArticle.objects.insert_ignore(**values)


def test_next_crawl_ms_prefers_the_interval(source: NewsSource) -> None:
    now = int(datetime(2026, 8, 28, 12, 5, tzinfo=UTC).timestamp() * 1000)

    source.crawl_interval_minutes = 0
    daily = next_crawl_ms(source, now)

    source.crawl_interval_minutes = 30
    interval = next_crawl_ms(source, now)

    assert interval == int(datetime(2026, 8, 28, 12, 30, tzinfo=UTC).timestamp() * 1000)
    assert interval < daily, "주기가 설정되면 하루 한 번보다 먼저 돌아야 한다"

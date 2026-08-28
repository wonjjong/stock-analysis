"""
수집 오케스트레이션의 DB 쪽. `app/lib/news-crawler.ts` 의 crawlSource /
crawlDueSources 이식.

## 트랜잭션 경계를 원본과 같게 둔다

원본은 `실행 중` 런 행을 네트워크 I/O **전에** 커밋한다. 전체를 한 트랜잭션으로 감싸면

1. 진행 중인 실행이 다른 커넥션에서 보이지 않고
2. 최대 10페이지 x 12초 동안 트랜잭션이 열려 autovacuum 을 방해한다

그래서 여기서도 런 행을 먼저 커밋하고, I/O 를 트랜잭션 밖에서 하고, 기사·소스 갱신
블록만 짧은 `atomic()` 으로 묶는다.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import transaction

from news.crawler.analysis import analyze_news_locally
from news.crawler.fetcher import CrawlError, build_client
from news.crawler.jsurl import InvalidSourceUrl
from news.crawler.pipeline import fetch_source_items
from news.crawler.schedule import next_interval_run_at, next_run_at
from news.crawler.types import SourceSpec
from news.crawler.window import select_recent_items
from news.models import CrawlStatus, InsightStatus, NewsArticle, NewsCrawlRun, NewsSource

logger = logging.getLogger(__name__)

DUE_LIMIT = 20


@dataclass(slots=True)
class CrawlResult:
    source_id: int
    fetched_count: int
    inserted_count: int
    status: str
    error: str | None = None


def _at(ms: int | None) -> datetime | None:
    """정수 밀리초 → aware datetime. 파서는 ms 도메인이고 컬럼은 timestamptz 다."""
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _content_hash(title: str, excerpt: str) -> str:
    """TS 는 `crypto.subtle.digest("SHA-256", title + "\\n" + excerpt)` 를 쓴다."""
    return hashlib.sha256(f"{title}\n{excerpt}".encode()).hexdigest()


def _error_message(reason: BaseException) -> str:
    if isinstance(reason, (CrawlError, InvalidSourceUrl)):
        return str(reason)[:500]
    if isinstance(reason, Exception):
        return str(reason)[:500] or "알 수 없는 수집 오류가 발생했습니다."
    return "알 수 없는 수집 오류가 발생했습니다."


def _spec(source: NewsSource) -> SourceSpec:
    return SourceSpec(
        id=source.pk,
        url=source.url,
        resolved_url=source.resolved_url,
        max_pages=source.max_pages,
        window_hours=source.window_hours,
        etag=source.etag,
        last_modified=source.last_modified,
    )


def next_crawl_ms(source: NewsSource, now_ms: int) -> int:
    """주기가 설정돼 있으면 주기 경계, 아니면 하루 한 번 `crawl_hour_kst`."""
    if source.crawl_interval_minutes > 0:
        return next_interval_run_at(source.crawl_interval_minutes, now_ms)
    return next_run_at(source.crawl_hour_kst, now_ms)


def crawl_source(source_id: int) -> CrawlResult:
    source = NewsSource.objects.filter(pk=source_id, is_active=True).first()
    if source is None:
        raise CrawlError("활성화된 뉴스 소스를 찾지 못했습니다.")

    started_ms = _now_ms()
    started_at = _at(started_ms)
    # 네트워크 I/O 전에 커밋한다. 진행 중인 실행이 보여야 reaper 와 화면이 동작한다.
    run = NewsCrawlRun.objects.create(
        source=source, status=CrawlStatus.RUNNING, started_at=started_at
    )

    try:
        with build_client() as client:
            fetched = fetch_source_items(client, _spec(source), started_ms)
        next_ms = next_crawl_ms(source, started_ms)

        if fetched.unchanged:
            with transaction.atomic():
                NewsSource.objects.filter(pk=source.pk).update(
                    last_status=CrawlStatus.NOT_MODIFIED,
                    last_error=None,
                    last_crawled_at=started_at,
                    next_crawl_at=_at(next_ms),
                    updated_at=started_at,
                )
                NewsCrawlRun.objects.filter(pk=run.pk).update(
                    status=CrawlStatus.NOT_MODIFIED, completed_at=_at(_now_ms())
                )
            return CrawlResult(source.pk, 0, 0, CrawlStatus.NOT_MODIFIED)

        items = select_recent_items(fetched.items, started_ms, source.window_hours)
        completed_status = CrawlStatus.DONE if items else CrawlStatus.EMPTY

        inserted = 0
        for item in items:
            analysis_text = f"{item.title}. {item.excerpt}"[:6500]
            analysis = analyze_news_locally(analysis_text, "MARKET", "시장 전체")
            # published_date_kst 는 DB 생성 열이므로 쓰지 않는다.
            # ON CONFLICT DO NOTHING 의 영향 행 수가 곧 신규 저장 건수다.
            inserted += NewsArticle.objects.insert_ignore(
                source_id=source.pk,
                symbol="GENERAL",
                title=item.title,
                canonical_url=item.url,
                excerpt=item.excerpt,
                published_at=_at(item.published_at),
                content_hash=_content_hash(item.title, item.excerpt),
                sentiment=analysis["sentiment"],
                sentiment_score=round(analysis["sentimentScore"]),
                materiality=analysis["materiality"],
                relevance=100,
                event_type=analysis["eventType"],
                score_adjustment=analysis["scoreAdjustment"],
                analysis_summary=analysis["summary"],
                collected_at=started_at,
                insight_status=InsightStatus.PENDING,
            )

        with transaction.atomic():
            NewsSource.objects.filter(pk=source.pk).update(
                resolved_url=fetched.url,
                etag=fetched.etag,
                last_modified=fetched.last_modified,
                last_status=completed_status,
                last_error=None,
                last_crawled_at=started_at,
                next_crawl_at=_at(next_ms),
                updated_at=started_at,
            )
            NewsCrawlRun.objects.filter(pk=run.pk).update(
                status=completed_status,
                fetched_count=len(items),
                inserted_count=inserted,
                completed_at=_at(_now_ms()),
            )
        return CrawlResult(source.pk, len(items), inserted, completed_status)

    except BaseException as reason:
        message = _error_message(reason)
        with transaction.atomic():
            NewsSource.objects.filter(pk=source.pk).update(
                last_status=CrawlStatus.ERROR,
                last_error=message,
                last_crawled_at=started_at,
                next_crawl_at=_at(next_crawl_ms(source, started_ms)),
                updated_at=started_at,
            )
            NewsCrawlRun.objects.filter(pk=run.pk).update(
                status=CrawlStatus.ERROR, error=message, completed_at=_at(_now_ms())
            )
        raise CrawlError(message) from reason


def crawl_due_sources(limit: int = DUE_LIMIT) -> list[CrawlResult]:
    """
    기한이 된 소스를 순차 처리한다.

    원본과 같이 순차다 — 소스 안의 페이지네이션이 본질적으로 순차이고(다음 페이지 URL 이
    이전 페이지 HTML 에서 나온다) 소스 수가 적어 병렬화 이득이 없다. 워커를 늘려
    병렬화하려면 `SELECT … FOR UPDATE SKIP LOCKED` 와 lease 컬럼이 필요하다.
    """
    now = datetime.now(tz=UTC)
    due = list(
        NewsSource.objects.filter(is_active=True, next_crawl_at__lte=now)
        .order_by("next_crawl_at")
        .values_list("pk", flat=True)[:limit]
    )

    results: list[CrawlResult] = []
    for source_id in due:
        try:
            results.append(crawl_source(source_id))
        except (CrawlError, InvalidSourceUrl) as reason:
            logger.warning("소스 %s 수집 실패: %s", source_id, reason)
            results.append(CrawlResult(source_id, 0, 0, CrawlStatus.ERROR, str(reason)))
    return results


def reap_stuck_runs(older_than_minutes: int = 30) -> int:
    """
    `실행 중` 으로 멈춘 런을 닫는다. 프로세스가 죽으면 그 상태가 영구히 남고, 그 값이
    크롤 동작 여부의 유일한 관측 수단이라 썩으면 안 된다. 원본에는 없던 보강이다.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=older_than_minutes)
    return NewsCrawlRun.objects.filter(
        status=CrawlStatus.RUNNING, started_at__lt=cutoff
    ).update(
        status=CrawlStatus.ERROR,
        error="실행이 비정상 종료되어 자동으로 닫혔습니다.",
        completed_at=datetime.now(tz=UTC),
    )

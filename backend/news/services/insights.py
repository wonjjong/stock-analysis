"""
본문 분석 큐. `app/lib/news-insights.ts` 의 DB 부분 이식
(processArticle / markFailure / processPendingInsights / insightQueueStats).

수집기는 목록과 요약만 저장하므로, 종목·시황 분석에 쓸 근거는 이 큐가 만든다. 기사마다
`insight_status` 가 `대기` 로 들어가고 스케줄러가 한 배치씩 소화한다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from django.db import connection, transaction

from news.crawler.body import BodyError, fetch_article_body
from news.crawler.fetcher import build_client
from news.crawler.insights import (
    LLM_BODY_LIMIT,
    SYSTEM_PROMPT,
    Insight,
    deserves_llm,
    llm_insight,
    rule_insight,
)
from news.crawler.jsurl import InvalidSourceUrl
from news.crawler.symbols import match_symbols
from news.models import InsightStatus, NewsArticle, NewsArticleSymbol
from news.services.llm import is_configured, llm_json_with_failover

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
DEFAULT_BATCH = 12
MAX_BATCH = 50


@dataclass(slots=True)
class ProcessSummary:
    picked: int = 0
    done: int = 0
    llm: int = 0
    rule: int = 0
    failed: int = 0
    providers: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "picked": self.picked,
            "done": self.done,
            "llm": self.llm,
            "rule": self.rule,
            "failed": self.failed,
            "providers": self.providers,
        }


def _upsert_insight(article_id: int, insight: Insight, body_chars: int, now: datetime) -> None:
    """
    `ON CONFLICT (article_id) DO UPDATE` 로 갱신하며 `attempts` 를 누적한다.

    jsonb 는 읽기와 쓰기가 비대칭이다 — 드라이버는 조회 결과를 파싱된 배열로 주지만,
    파라미터로 받은 Python 리스트는 Postgres 배열 리터럴로 직렬화해 jsonb 파싱이
    실패한다. 그래서 쓰기에는 JSON 문자열을 넘긴다.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO news_insights
              (article_id, summary, keywords, sectors, evidence, sentiment, sentiment_score,
               materiality, event_type, impact_horizon, market_view, body_chars, engine, model,
               attempts, error, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, NULL, %s, %s)
            ON CONFLICT (article_id) DO UPDATE SET
              summary = excluded.summary, keywords = excluded.keywords,
              sectors = excluded.sectors, evidence = excluded.evidence,
              sentiment = excluded.sentiment, sentiment_score = excluded.sentiment_score,
              materiality = excluded.materiality, event_type = excluded.event_type,
              impact_horizon = excluded.impact_horizon, market_view = excluded.market_view,
              body_chars = excluded.body_chars, engine = excluded.engine,
              model = excluded.model, attempts = news_insights.attempts + 1,
              error = NULL, updated_at = excluded.updated_at
            """,
            [
                article_id,
                insight.summary,
                json.dumps(insight.keywords, ensure_ascii=False),
                json.dumps(insight.sectors, ensure_ascii=False),
                json.dumps(insight.evidence, ensure_ascii=False),
                insight.sentiment,
                insight.sentiment_score,
                insight.materiality,
                insight.event_type,
                insight.impact_horizon,
                insight.market_view,
                body_chars,
                insight.engine,
                insight.model,
                now,
                now,
            ],
        )


def _mark_failure(article_id: int, message: str, now: datetime) -> None:
    """
    실패를 기록하고 시도 횟수에 따라 상태를 정한다. MAX_ATTEMPTS 를 넘기면 `오류` 로
    고정해 큐에서 빠지고, 그 전이면 `대기` 로 되돌려 다음 배치가 다시 시도한다.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attempts FROM news_insights WHERE article_id = %s", [article_id]
        )
        row = cursor.fetchone()
        attempts = (row[0] if row else 0) + 1
        cursor.execute(
            """
            INSERT INTO news_insights (article_id, attempts, error, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (article_id) DO UPDATE SET
              attempts = %s, error = excluded.error, updated_at = excluded.updated_at
            """,
            [article_id, attempts, message[:400], now, now, attempts],
        )
    status = InsightStatus.ERROR if attempts >= MAX_ATTEMPTS else InsightStatus.PENDING
    NewsArticle.objects.filter(pk=article_id).update(insight_status=status)


def _replace_symbols(article_id: int, title: str, body: str, now: datetime) -> list:
    matches = match_symbols(title, body)
    NewsArticleSymbol.objects.filter(article_id=article_id).delete()
    if matches:
        NewsArticleSymbol.objects.bulk_create(
            [
                NewsArticleSymbol(
                    article_id=article_id,
                    symbol=match.symbol,
                    company=match.company,
                    market=match.market,
                    sector=match.sector,
                    match_type=match.match_type,
                    mentions=match.mentions,
                    relevance=match.relevance,
                    created_at=now,
                )
                for match in matches
            ]
        )
    return matches


def process_article(article: NewsArticle, use_llm: bool, now: datetime) -> tuple[bool, str]:
    """한 기사를 분석해 저장한다. (LLM 사용 여부, 공급자명) 를 돌려준다."""
    body = article.excerpt or ""
    with build_client() as client:
        try:
            fetched = fetch_article_body(client, article.canonical_url)
            if fetched.chars > len(body):
                body = fetched.text
        except (BodyError, InvalidSourceUrl):
            # 본문 페이지를 못 읽으면 수집 당시의 요약으로 분석을 이어간다.
            pass

    base = rule_insight(article.title, body)
    insight = base
    provider_name = ""

    symbols = match_symbols(article.title, body)
    if use_llm and deserves_llm(base, symbols, len(body)):
        user = json.dumps(
            {"title": article.title, "article": body[:LLM_BODY_LIMIT]}, ensure_ascii=False
        )
        chain = llm_json_with_failover(SYSTEM_PROMPT, user, now)
        if chain.parsed is not None and chain.provider_name:
            insight = llm_insight(
                chain.parsed if isinstance(chain.parsed, dict) else {},
                base,
                chain.provider_name,
                "",
            )
            provider_name = chain.provider_name
        # 모든 공급자가 실패하면 규칙 기반 결과를 그대로 쓴다. 기사는 완료로 남는다.

    with transaction.atomic():
        _upsert_insight(article.pk, insight, len(body), now)
        _replace_symbols(article.pk, article.title, body, now)
        top = symbols[0] if symbols else None
        NewsArticle.objects.filter(pk=article.pk).update(
            insight_status=InsightStatus.DONE,
            sentiment=insight.sentiment,
            sentiment_score=insight.sentiment_score,
            materiality=insight.materiality,
            event_type=insight.event_type,
            score_adjustment=insight.score_adjustment,
            analysis_summary=insight.summary[:500],
            relevance=top.relevance if top else 40,
            symbol=top.symbol if top else "GENERAL",
        )

    return bool(provider_name), provider_name


def process_pending_insights(
    limit: int = DEFAULT_BATCH, now: datetime | None = None
) -> ProcessSummary:
    """대기 중인 기사를 정해진 개수만큼 분석한다. 스케줄러와 수동 실행이 같은 함수를 쓴다."""
    now = now or datetime.now(tz=UTC)
    size = max(1, min(MAX_BATCH, int(limit)))
    queue = list(
        NewsArticle.objects.filter(insight_status=InsightStatus.PENDING)
        .order_by("-published_at", "-collected_at")[:size]
    )

    use_llm = is_configured()
    summary = ProcessSummary(picked=len(queue))

    for article in queue:
        try:
            llm_used, provider = process_article(article, use_llm, now)
        except Exception as reason:
            summary.failed += 1
            logger.warning("기사 %s 본문 분석 실패: %s", article.pk, reason)
            _mark_failure(article.pk, str(reason) or "본문 분석에 실패했습니다.", now)
            continue
        summary.done += 1
        if llm_used:
            summary.llm += 1
            summary.providers[provider] = summary.providers.get(provider, 0) + 1
        else:
            summary.rule += 1

    return summary


def insight_queue_stats() -> dict[str, object]:
    from django.db.models import Count

    from news.models import NewsInsight

    counts = {
        row["insight_status"]: row["n"]
        for row in NewsArticle.objects.values("insight_status").annotate(n=Count("id"))
    }
    engines = {
        row["engine"]: row["n"]
        for row in NewsInsight.objects.values("engine").annotate(n=Count("id"))
    }
    return {
        "pending": counts.get(InsightStatus.PENDING, 0),
        "done": counts.get(InsightStatus.DONE, 0),
        "failed": counts.get(InsightStatus.ERROR, 0),
        "engines": engines,
        "llmConfigured": is_configured(),
    }

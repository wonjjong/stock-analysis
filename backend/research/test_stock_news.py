from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from research.analysis import Evidence
from research.scoring import news_score
from research.stock_news import NewsItem, NewsProviderStatus, StockNewsQuery, select_news

NOW = datetime(2026, 9, 8, tzinfo=UTC)
QUERY = StockNewsQuery("005930", "KR", "삼성전자", ("Samsung Electronics",),
                       NOW - timedelta(days=30), NOW)


def item(title="삼성전자 실적 성장", *, url="https://news.example/a", provider="Naver",
         score=None, date=NOW):
    return NewsItem(Evidence("source:1", "news", title, provider, date.isoformat(),
                             NOW.isoformat(), "", url), provider, score)


def test_query_includes_ticker_company_and_aliases():
    assert {"005930", "삼성전자", "Samsung Electronics"} <= set(QUERY.terms)
    with pytest.raises(ValueError):
        replace(QUERY, until=QUERY.since)


def test_db_insight_wins_over_tracking_url_duplicate():
    external = item(url="https://news.example/a?utm_source=naver")
    db = item(provider="DB", score=87)
    context = select_news(QUERY, [external, db],
                          [NewsProviderStatus("DB"), NewsProviderStatus("Naver")])
    assert len(context.items) == 1
    assert context.items[0].provider == "DB"
    assert context.sentiment_scores == [87]
    assert context.providers[0].accepted == 1
    assert context.providers[1].accepted == 0


def test_url_less_titles_dedupe_but_distinct_urls_are_preserved():
    context = select_news(QUERY, [item(url=""), item(title="삼성전자: 실적 성장!", url=""),
                                  item(url="https://other.example/b")], [])
    assert len(context.items) == 2
    assert len({e.id for e in context.evidence}) == 2


def test_irrelevant_stale_future_and_unknown_dates_are_rejected():
    rows = [item("현대차 실적 성장"), item(date=NOW - timedelta(days=31)),
            item(date=NOW + timedelta(seconds=1)),
            replace(item(), evidence=replace(item().evidence, observed_at="unknown"))]
    context = select_news(QUERY, rows, [])
    assert not context.items
    assert news_score(context.sentiment_scores) == (50, 0)
    assert context.data_gaps


def test_related_company_and_ambiguous_short_ticker_do_not_match():
    kakao = replace(QUERY, symbol="035720", company="카카오", aliases=())
    assert not select_news(kakao, [item("카카오뱅크 실적 성장")], []).items
    arm = replace(QUERY, symbol="ARM", market="US", company="Arm Holdings", aliases=())
    assert not select_news(arm, [item("Patient suffers arm injury")], []).items
    assert select_news(arm, [item("NASDAQ:ARM earnings beat estimates")], []).items


def test_limit_and_latest_order_and_scores_agree_with_evidence():
    rows = [item(url=f"https://news.example/{i}", date=NOW - timedelta(hours=i))
            for i in range(20)]
    context = select_news(QUERY, list(reversed(rows)), [NewsProviderStatus("Naver", fetched=20)])
    assert len(context.evidence) == len(context.sentiment_scores) == 12
    assert context.evidence[0].url.endswith("/0")
    assert context.evidence[-1].url.endswith("/11")
    assert all(score > 50 for score in context.sentiment_scores)
    assert context.providers[0].accepted == 12

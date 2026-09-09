"""종목 뉴스 수집의 장애·캐시 및 HTML/API 공통 분석 계약 검증."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from django.core.cache import cache
from django.db import DatabaseError
from django.test import RequestFactory

from research.analysis import Evidence
from research.indicators import indicators_ai_context
from research.lab_preview import build_lab_preview
from research.recommendation import MacroRegime
from research.services import stock_analysis, stock_news
from research.services.news_search import NewsSearchError
from research.stock_news import NewsItem, NewsProviderStatus, StockNewsContext, StockNewsQuery


@pytest.fixture
def query(monkeypatch):
    now = datetime(2026, 9, 8, 3, tzinfo=UTC)
    value = StockNewsQuery("AAPL", "US", "Apple Inc.", ("Apple",), now - timedelta(days=30), now)
    monkeypatch.setattr(stock_news, "build_news_query", lambda *_: value)
    cache.clear()
    yield value
    cache.clear()


def article(query, *, provider="GDELT", score=80, url="https://example.com/apple"):
    return NewsItem(
        Evidence(
            "source:1",
            "news",
            "Apple earnings rise",
            provider,
            query.until.isoformat(),
            query.until.isoformat(),
            "Apple reports record profit",
            url,
        ),
        provider,
        score,
    )


def test_cached_external_results_still_refresh_stored_news(monkeypatch, query):
    stored = Mock(return_value=())
    monkeypatch.setattr(stock_news, "stored_news", stored)
    search = SimpleNamespace(provider="GDELT", search=Mock(return_value=(article(query),)))
    first = stock_news.collect_stock_news("AAPL", "Apple Inc.", [], search=search)
    stored.return_value = (article(query, provider="DB", score=23),)
    second = stock_news.collect_stock_news("AAPL", "Apple Inc.", [], search=search)

    assert search.search.call_count == 1
    assert stored.call_count == 2
    assert first.sentiment_scores == [80]
    assert second.sentiment_scores == [23]
    assert second.items[0].provider == "DB"
    assert second.providers[-1].cached is True
    assert second.providers[-1].accepted == 0


def test_partial_failure_retains_yahoo_and_is_retried(monkeypatch, query):
    monkeypatch.setattr(stock_news, "stored_news", Mock(side_effect=DatabaseError("offline")))
    search = SimpleNamespace(provider="GDELT", search=Mock(side_effect=NewsSearchError("timeout")))
    yahoo = article(query, provider="Yahoo").evidence
    failed = stock_news.collect_stock_news("AAPL", "Apple Inc.", [yahoo], search=search)
    search.search.side_effect = None
    search.search.return_value = ()
    recovered = stock_news.collect_stock_news("AAPL", "Apple Inc.", [yahoo], search=search)

    assert len(failed.evidence) == 1
    assert failed.items[0].provider == "Yahoo"
    assert any("GDELT" in gap for gap in failed.data_gaps)
    assert any("DB" in gap for gap in failed.data_gaps)
    assert search.search.call_count == 2
    assert recovered.providers[-1].status == "success"


@pytest.fixture
def context_dependencies(monkeypatch, query):
    preview = build_lab_preview()
    snapshot = replace(preview["result"]["snapshot"], symbol="AAPL", company="Apple Inc.")
    market = replace(preview["evidence"][0], id="market:1")
    filing = replace(preview["evidence"][1], id="filing:1")
    yahoo = article(query, provider="Yahoo").evidence
    news = StockNewsContext((article(query),), (NewsProviderStatus("GDELT", accepted=1),))
    monkeypatch.setattr(
        stock_analysis, "fetch_market_snapshot", Mock(return_value=(snapshot, [market, yahoo]))
    )
    monkeypatch.setattr(
        stock_analysis,
        "fetch_filing_context",
        AsyncMock(return_value=SimpleNamespace(evidence=[filing], fundamentals=None)),
    )
    collect = Mock(return_value=news)
    monkeypatch.setattr(stock_analysis, "collect_stock_news", collect)
    return preview, snapshot, market, filing, news, collect


def test_common_context_scores_exactly_selected_news(context_dependencies):
    _, snapshot, market, filing, news, collect = context_dependencies
    context = stock_analysis.collect_stock_context("AAPL")

    assert context.snapshot is snapshot
    assert context.scores.news == 80
    assert context.scores.news_observations == 1
    assert context.evidence == [market, filing, *news.evidence]
    assert collect.call_args.args[:2] == ("AAPL", "Apple Inc.")
    assert collect.call_args.args[2][0].source == "Yahoo"


def test_no_news_preserves_neutral_score_and_zero_observations(context_dependencies):
    *_, collect = context_dependencies
    collect.return_value = StockNewsContext()
    context = stock_analysis.collect_stock_context("AAPL")
    assert context.scores.news == 50
    assert context.scores.news_observations == 0
    assert all(e.kind != "news" for e in context.evidence)
    assert context.news.data_gaps


def test_live_and_ranked_analysis_share_news_context(monkeypatch, context_dependencies):
    preview, *_ = context_dependencies
    context = stock_analysis.collect_stock_context("AAPL")
    collect = Mock(return_value=context)
    monkeypatch.setattr(stock_analysis, "collect_stock_context", collect)
    regime = MacroRegime(18, 0, 0, 0)
    monkeypatch.setattr(stock_analysis, "fetch_macro_regime", lambda: SimpleNamespace(regime=regime))
    live_report = Mock(return_value=(preview["result"]["report"], []))
    ranked_report = Mock(return_value=(SimpleNamespace(as_dict=lambda: {"engine": "test"}), []))
    monkeypatch.setattr(stock_analysis, "create_live_report", live_report)
    monkeypatch.setattr(stock_analysis, "create_report", ranked_report)

    live = stock_analysis.analyze_live_stock("AAPL")
    ranked = stock_analysis.analyze_ranked_stock("AAPL", [context.scores.as_candidate()], regime)

    assert collect.call_count == 2
    assert ranked is not None
    assert live["result"]["news_search"] == ranked["newsSearch"] == context.news.as_dict()
    assert live_report.call_args.args[1] == ranked_report.call_args.args[3] == context.evidence
    assert live_report.call_args.args[2]["newsObservations"] == 1
    assert live["result"]["indicators"] == ranked["indicators"]
    compact = indicators_ai_context(ranked["indicators"])
    assert live_report.call_args.args[2]["indicators"] == compact
    assert ranked_report.call_args.args[1]["indicators"] == compact
    assert ranked_report.call_args.args[1]["news_observations"] == 1
    assert ranked_report.call_args.args[1]["news"] == 80


def test_live_ai_report_is_cached_for_identical_evidence(monkeypatch, context_dependencies):
    preview, *_ = context_dependencies
    context = stock_analysis.collect_stock_context("AAPL")
    noisy_details = {**context.snapshot.financial_details, "forwardPE": 19.201}
    noisy_snapshot = replace(
        context.snapshot,
        market_cap=(context.snapshot.market_cap or 12_400_000_000) * 1.00005,
        financial_details=noisy_details,
    )
    noisy_evidence = [replace(item, available_at="2026-09-09T02:00:00+00:00") for item in context.evidence]
    noisy_context = replace(context, snapshot=noisy_snapshot, evidence=noisy_evidence)
    monkeypatch.setattr(
        stock_analysis,
        "collect_stock_context",
        Mock(side_effect=[context, noisy_context]),
    )
    monkeypatch.setattr(
        stock_analysis,
        "fetch_macro_regime",
        lambda: SimpleNamespace(regime=MacroRegime(18, 0, 0, 0)),
    )
    create = Mock(return_value=(preview["result"]["report"], [{"kind": "성공"}]))
    monkeypatch.setattr(stock_analysis, "create_live_report", create)

    first = stock_analysis.analyze_live_stock("AAPL")
    second = stock_analysis.analyze_live_stock("AAPL")

    assert create.call_count == 1
    assert first["result"]["report"] == second["result"]["report"]
    assert first["attempts"] == [{"kind": "성공"}]
    assert second["attempts"][0]["kind"] == "캐시"


def test_preview_renders_without_collecting_or_analyzing(monkeypatch):
    from research import views

    forbidden = Mock(side_effect=AssertionError("preview must not invoke analysis"))
    monkeypatch.setattr(views, "analyze_live_stock", forbidden)
    monkeypatch.setattr(stock_analysis, "collect_stock_context", forbidden)
    monkeypatch.setattr(stock_news, "collect_stock_news", forbidden)
    response = views.stock_lab_preview(RequestFactory().get("/research/lab/preview"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "미리보기" in html
    assert 'class="stock-lab-results"' in html
    assert 'data-signed-value="0.4"' in html
    forbidden.assert_not_called()


def test_yahoo_cache_skips_news_fetch_but_refreshes_market(monkeypatch, context_dependencies):
    _, snapshot, market, _, news, collect = context_dependencies
    yahoo_fetch = Mock(return_value=news.evidence)
    monkeypatch.setattr(stock_analysis, "_news_evidence", yahoo_fetch)

    def market_fetch(symbol, *, news_errors, news_loader):
        return snapshot, [market, *news_loader(SimpleNamespace(ticker=symbol), snapshot.observed_at)]

    market_fetch_mock = Mock(side_effect=market_fetch)
    monkeypatch.setattr(stock_analysis, "fetch_market_snapshot", market_fetch_mock)
    stock_analysis.collect_stock_context("AAPL")
    assert collect.call_args.kwargs["yahoo_cached"] is False
    stock_analysis.collect_stock_context("AAPL")
    assert collect.call_args.kwargs["yahoo_cached"] is True
    assert market_fetch_mock.call_count == 2
    assert yahoo_fetch.call_count == 1
    assert yahoo_fetch.call_args.kwargs["limit"] == 50


def test_yahoo_failure_does_not_prevent_market_snapshot(monkeypatch):
    import pandas as pd

    from research import market_data

    history = pd.DataFrame(
        {
            "Close": [100.0, 102.0, 101.0],
            "High": [103.0, 104.0, 103.0],
            "Low": [99.0, 100.0, 100.0],
            "Volume": [1000, 1000, 1000],
        },
        index=pd.date_range("2026-09-01", periods=3, tz="UTC"),
    )
    ticker = SimpleNamespace(ticker="AAPL", info={"longName": "Apple Inc."})
    monkeypatch.setattr(market_data, "_load_ticker", lambda _: ("AAPL", ticker, history))
    financials = dict.fromkeys(
        (
            "total_revenue",
            "net_income",
            "ebitda",
            "cash_and_short_term_investments",
            "total_debt",
            "operating_cash_flow",
            "capital_expenditure",
        )
    )
    monkeypatch.setattr(market_data, "_statement_values", lambda _: (financials, ""))
    errors = []
    snapshot, evidence = market_data.fetch_market_snapshot(
        "AAPL", news_errors=errors, news_loader=Mock(side_effect=TimeoutError("offline"))
    )
    assert snapshot.price == 101
    assert errors == ["Yahoo 종목 뉴스 조회 실패"]
    assert all(e.kind != "news" for e in evidence)

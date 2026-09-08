"""팩터 점수 계산 검증. 네트워크도 DB도 쓰지 않는 순수 함수 검증이다."""

from __future__ import annotations

import pytest

from research.fundamentals import FundamentalMetrics
from research.scoring import (
    CORE_INPUTS,
    NEUTRAL,
    interpolate,
    news_score,
    score_snapshot,
)

FULL = {
    "symbol": "005930.KS",
    "price": 78000.0,
    "currency": "KRW",
    "atr_20": 2400.0,
    "beta": 1.05,
    "return_1m_pct": 5.0,
    "return_6m_pct": 18.0,
    "return_1y_pct": 42.0,
    "distance_from_high_pct": -8.0,
    "volatility_20d_pct": 24.0,
    "trailing_pe": 13.2,
    "price_to_book": 1.4,
    "gross_margin_pct": 38.0,
    "profit_margin_pct": 12.0,
    "revenue_growth_pct": 9.0,
    "avg_volume_20d": 12_000_000.0,
    "max_drawdown_1y_pct": -21.5,
}


def test_interpolate_clamps_outside_the_curve():
    curve = ((0.0, 0.0), (10.0, 100.0))
    assert interpolate(-5, curve) == 0
    assert interpolate(15, curve) == 100
    assert interpolate(5, curve) == 50


def test_missing_metrics_fall_back_to_neutral_not_zero():
    """없는 값을 0 으로 치면 그 종목이 부당하게 바닥으로 간다."""
    scores = score_snapshot({"symbol": "X", "price": 10.0})
    assert scores.momentum == NEUTRAL
    assert scores.value == NEUTRAL
    assert scores.coverage["momentum"] == 0


def test_drawdown_sign_is_flipped_for_the_ranker():
    """스냅샷은 -21.5 로 주지만 rank_candidates 는 '클수록 나쁨'인 양수를 받는다."""
    assert score_snapshot(FULL).drawdown == pytest.approx(21.5)


def test_cheap_stock_scores_higher_on_value():
    cheap = score_snapshot({**FULL, "trailing_pe": 6.0, "price_to_book": 0.6})
    rich = score_snapshot({**FULL, "trailing_pe": 55.0, "price_to_book": 9.0})
    assert cheap.value > rich.value


def test_dart_financials_override_market_financials_but_not_price_history():
    dart = FundamentalMetrics(
        source="DART",
        period="2025-12-31",
        trailing_pe=6,
        price_to_book=0.6,
        profit_margin_pct=22,
        revenue_growth_pct=24,
    )

    scores = score_snapshot({**FULL, "trailing_pe": 55, "price_to_book": 9}, fundamentals=dart)

    assert scores.financial_source == "DART"
    assert scores.financial_period == "2025-12-31"
    assert scores.value > 90
    assert scores.quality > score_snapshot(FULL).quality


def test_same_turnover_number_scores_lower_in_won():
    """원화와 달러는 자릿수가 1,000배 넘게 다르다. 거래대금 1억은 달러면 크고 원화면 작다."""
    krw = score_snapshot({**FULL, "currency": "KRW", "price": 100.0, "avg_volume_20d": 1e6})
    usd = score_snapshot({**FULL, "currency": "USD", "price": 100.0, "avg_volume_20d": 1e6})
    assert krw.liquidity < usd.liquidity


def test_economically_similar_turnover_scores_alike_across_currencies():
    """통화별 기준선을 두는 목적이다. 환율을 지어내지 않고도 비교가 가능해야 한다."""
    krw = score_snapshot({**FULL, "currency": "KRW", "price": 78000.0, "avg_volume_20d": 1e6})
    usd = score_snapshot({**FULL, "currency": "USD", "price": 78.0, "avg_volume_20d": 1e6})
    assert abs(krw.liquidity - usd.liquidity) < 5


def test_stale_ratio_ignores_missing_fundamentals():
    """yfinance 는 한국 종목의 PER·PBR 을 주지 않는다. 그것 때문에 순위에서 빠지면 안 된다."""
    dropped = ("trailing_pe", "price_to_book")
    without_fundamentals = {key: value for key, value in FULL.items() if key not in dropped}
    scores = score_snapshot(without_fundamentals)
    assert scores.stale_ratio == 0
    assert scores.coverage["value"] == 0


def test_stale_ratio_rises_when_price_history_is_missing():
    scores = score_snapshot({"symbol": "X", "price": 10.0})
    assert scores.stale_ratio == pytest.approx(1 - 1 / len(CORE_INPUTS))


def test_news_score_averages_sentiment_and_is_neutral_without_articles():
    assert news_score([80, 60]) == (70.0, 2)
    assert news_score([]) == (NEUTRAL, 0)


def test_news_observation_count_is_carried_to_the_ranker_and_ai_context():
    scores = score_snapshot(FULL, sentiment_scores=[80, 60])

    assert scores.news_observations == 2
    assert scores.as_candidate().news_observations == 2
    assert scores.as_ai_context()["newsObservations"] == 2


def test_revisions_stay_neutral_because_no_public_source_exists():
    scores = score_snapshot(FULL)
    assert scores.revisions == NEUTRAL
    assert scores.coverage["revisions"] == 0


def test_as_candidate_carries_every_ranker_input():
    candidate = score_snapshot(FULL, sentiment_scores=[70]).as_candidate()
    assert candidate.symbol == "005930.KS"
    assert candidate.liquidity > 0
    assert candidate.news == 70

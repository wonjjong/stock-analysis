"""외부 호출 없이 종목 분석실 UI를 확인하기 위한 고정 샘플 데이터."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from math import sin
from typing import Any

from research.analysis import Evidence, LiveStockReport
from research.market_data import MarketSnapshot, moving_averages, price_chart_points
from research.recommendation import MacroRegime, trade_plan
from research.scoring import score_snapshot


def build_lab_preview() -> dict[str, Any]:
    """AI·시세·공시 호출 없이 분석 결과 화면에 필요한 샘플을 만든다."""
    started_at = date(2026, 3, 9)
    rows: list[tuple[str, float, float, float, float]] = []
    previous = 118.0
    for index in range(140):
        close = 118 + index * .22 + sin(index / 6) * 2.8
        opening = previous + sin(index * 1.7) * .8
        high = max(opening, close) + 1.15
        low = min(opening, close) - 1.15
        rows.append(
            ((started_at + timedelta(days=index)).isoformat(), opening, high, low, close)
        )
        previous = close

    price = rows[-1][4]
    averages = moving_averages([row[4] for row in rows], price)
    snapshot = MarketSnapshot(
        symbol="DEMO",
        company="미리보기 샘플 종목",
        exchange="SAMPLE MARKET",
        currency="USD",
        sector="샘플 데이터",
        observed_at=rows[-1][0],
        price=price,
        market_cap=12_400_000_000,
        return_1d_pct=.4,
        return_1m_pct=4.8,
        return_6m_pct=18.2,
        return_1y_pct=25.6,
        high_52w=151.0,
        distance_from_high_pct=-1.7,
        volatility_20d_pct=31.4,
        atr_20=2.35,
        moving_averages=averages,
        chart_points=price_chart_points(rows),
        max_drawdown_1y_pct=-18.3,
        avg_volume_20d=4_800_000,
        beta=1.15,
        trailing_pe=21.4,
        price_to_book=3.1,
        revenue_growth_pct=18.0,
        gross_margin_pct=42.0,
        profit_margin_pct=12.0,
        financial_period="2025-12-31",
        total_revenue=3_500_000_000,
        net_income=420_000_000,
        ebitda=720_000_000,
        cash_and_short_term_investments=610_000_000,
        total_debt=1_100_000_000,
        operating_cash_flow=510_000_000,
        capital_expenditure=-220_000_000,
    )
    scores = score_snapshot(snapshot.as_dict(), sentiment_scores=[62, 57, 66])
    plan = trade_plan(snapshot.price, snapshot.atr_20 or 0.0, MacroRegime(19, 0, 4, 0))
    evidence = [
        Evidence(
            id="preview:market",
            kind="market",
            title="샘플 가격·변동성 근거",
            source="미리보기 데이터",
            observed_at=snapshot.observed_at,
            available_at=snapshot.observed_at,
            summary="UI 확인용 고정 시세 데이터입니다.",
        ),
        Evidence(
            id="preview:filing",
            kind="financial",
            title="샘플 재무 근거",
            source="미리보기 데이터",
            observed_at="2025-12-31",
            available_at=snapshot.observed_at,
            summary="UI 확인용 고정 재무 데이터입니다.",
        ),
    ]
    evidence.extend(Evidence(
        id=f"preview:news:{provider}", kind="news", title=f"샘플 종목 뉴스 · {provider}",
        source=provider, observed_at=snapshot.observed_at, available_at=snapshot.observed_at,
        summary="UI 확인용 가상 뉴스입니다.",
    ) for provider in ("DB", "Yahoo", "GDELT"))
    report = LiveStockReport(
        symbol=snapshot.symbol,
        stance="중립",
        executive_summary="이 내용은 AI를 호출하지 않는 화면 미리보기용 샘플입니다.",
        bull_case=["20·60·100일 이평선이 정배열인 샘플 상태입니다."],
        bear_case=["실제 종목의 공시·뉴스·가격과 무관한 고정 데이터입니다."],
        catalysts=["실제 분석을 실행하면 수집 근거가 이 영역에 표시됩니다."],
        invalidation_conditions=["실제 분석에서는 ATR 기반 손절 기준을 근거와 함께 해석합니다."],
        data_gaps=["미리보기는 AI, 시세, SEC/DART, 뉴스 호출을 수행하지 않습니다."],
        evidence_ids=[item.id for item in evidence],
        engine="AI 미호출 미리보기",
    )
    return {
        "result": {
            "snapshot": snapshot,
            "report": report,
            "scores": scores,
            "trade_plan": plan,
            "news_search": {
                "periodDays": 30, "count": 3, "cacheTtlSeconds": 1200, "dataGaps": [],
                "providers": [
                    {"provider": name, "status": "success", "fetched": 1,
                     "accepted": 1, "cached": name == "GDELT", "detail": "미리보기 샘플"}
                    for name in ("DB", "Yahoo", "GDELT")
                ],
            },
            "chart": {
                "currency": snapshot.currency,
                "points": [asdict(point) for point in snapshot.chart_points],
                "tradePlan": plan.as_dict() if plan else None,
            },
        },
        "evidence": evidence,
        "attempts": [],
        "is_preview": True,
    }

"""HTML과 JSON 분석이 공유하는 시장·공시·뉴스 수집과 보고서 유스케이스."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace

from asgiref.sync import async_to_sync
from django.core.cache import cache

from research.analysis import Evidence, create_live_report, create_report
from research.fundamentals import FundamentalMetrics
from research.indicators import build_indicators, indicators_ai_context, valuation_inputs
from research.macro import fetch_macro_regime
from research.market_data import MarketSnapshot, _news_evidence, fetch_market_snapshot
from research.recommendation import rank_candidates, scoring_policy, trade_plan
from research.scoring import FactorScores, score_snapshot
from research.services.filings import fetch_filing_context
from research.services.stock_news import collect_stock_news
from research.stock_news import StockNewsContext
from research.symbols import route_symbol


@dataclass(frozen=True)
class StockAnalysisContext:
    snapshot: MarketSnapshot
    scores: FactorScores
    evidence: list[Evidence]
    news: StockNewsContext
    fundamentals: FundamentalMetrics | None = None


def _stable_cache_value(value):
    """공급자가 같은 조회에서 만드는 의미 없는 부동소수 잡음을 정규화한다."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            return format(number, ".4g")
    if isinstance(value, dict):
        return {key: _stable_cache_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_cache_value(item) for item in value]
    return value


def _live_report_cache_identity(snapshot, evidence, factors):
    evidence_identity = [
        {
            "id": item.id,
            "kind": item.kind,
            # 뉴스 ID가 같아도 제목·요약이 실제로 바뀌면 새 분석으로 본다.
            "summary": item.summary if item.kind == "news" else "",
        }
        for item in sorted(evidence, key=lambda row: row.id)
    ]
    return json.dumps(
        {
            "snapshot": _stable_cache_value(
                {
                    "symbol": snapshot.get("symbol"),
                    "observed_at": snapshot.get("observed_at"),
                    "price": snapshot.get("price"),
                    "financial_period": snapshot.get("financial_period"),
                }
            ),
            "evidence": evidence_identity,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def _create_cached_live_report(snapshot, evidence, factors):
    """동일 근거의 성공한 AI 해석을 20분 재사용해 중복 호출을 막는다."""
    identity = _live_report_cache_identity(snapshot, evidence, factors)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    key = f"research:live-report:v2:{digest}"
    cached = cache.get(key)
    if cached is not None:
        return cached, [{"name": cached.engine, "kind": "캐시", "detail": "20분 이내 동일 근거"}]
    created = create_live_report(snapshot, evidence, factors)
    if created[0].engine not in {"AI 미사용", "정량 폴백"}:
        cache.set(key, created[0], 1200)
    return created


def collect_stock_context(symbol: str) -> StockAnalysisContext:
    errors: list[str] = []
    yahoo_cached = False

    def yahoo_news(ticker, available_at):
        nonlocal yahoo_cached
        # 티커는 시세 조회에서 확정한 거래소 접미사까지 포함한다.
        key = f"research:yahoo-news:v1:{ticker.ticker}:30"
        rows = cache.get(key)
        if rows is not None:
            yahoo_cached = True
            return rows
        rows = _news_evidence(ticker, available_at, limit=50)
        cache.set(key, rows, 1200)
        return rows

    snapshot, evidence = fetch_market_snapshot(symbol, news_errors=errors, news_loader=yahoo_news)
    filing = async_to_sync(fetch_filing_context)(route_symbol(snapshot.symbol), snapshot.market_cap)
    news = collect_stock_news(
        snapshot.symbol,
        snapshot.company,
        [e for e in evidence if e.kind == "news"],
        yahoo_error="; ".join(errors),
        yahoo_cached=yahoo_cached,
    )
    scores = score_snapshot(
        snapshot.as_dict(), sentiment_scores=news.sentiment_scores, fundamentals=filing.fundamentals
    )
    return StockAnalysisContext(
        snapshot,
        scores,
        [e for e in evidence if e.kind != "news"] + list(filing.evidence) + news.evidence,
        news,
        filing.fundamentals,
    )


def analyze_live_stock(symbol: str) -> dict:
    context = collect_stock_context(symbol)
    snapshot = context.snapshot
    indicators = build_indicators(snapshot.as_dict(), context.fundamentals)
    plan = trade_plan(snapshot.price, snapshot.atr_20 or 0.0, fetch_macro_regime().regime)
    factors = {
        **context.scores.as_ai_context(),
        "tradePlan": plan.as_dict() if plan else None,
        "newsSearch": context.news.as_dict(),
        "indicators": indicators_ai_context(indicators),
    }
    report, attempts = _create_cached_live_report(snapshot.as_dict(), context.evidence, factors)
    report = replace(
        report,
        data_gaps=list(dict.fromkeys([*report.data_gaps, *context.news.data_gaps, *indicators["dataGaps"]])),
    )
    return {
        "result": {
            "snapshot": snapshot,
            "scores": context.scores,
            "report": report,
            "trade_plan": plan,
            "news_search": context.news.as_dict(),
            "indicators": indicators,
            "valuation_inputs": valuation_inputs(snapshot.as_dict()),
            "chart": {
                "currency": snapshot.currency,
                "points": [asdict(p) for p in snapshot.chart_points],
                "tradePlan": plan.as_dict() if plan else None,
            },
        },
        "evidence": context.evidence,
        "attempts": attempts,
    }


def analyze_ranked_stock(symbol, candidates, regime) -> dict | None:
    target = next((c for c in candidates if route_symbol(c.symbol).base == route_symbol(symbol).base), None)
    if target is None:
        return None
    context = collect_stock_context(target.symbol)
    indicators = build_indicators(context.snapshot.as_dict(), context.fundamentals)
    # 호출자가 준 후보의 가격·재무 계약을 유지하고 대상 뉴스만 갱신한다.
    target = replace(target, news=context.scores.news, news_observations=context.scores.news_observations)
    candidates = [target if c.symbol == target.symbol else c for c in candidates]
    recommendations = rank_candidates(candidates, regime, len(candidates))
    recommendation = next((r for r in recommendations if r["symbol"] == target.symbol), None)
    if recommendation is None:
        return None
    report, attempts = create_report(
        recommendation,
        {
            **asdict(target),
            "newsSearch": context.news.as_dict(),
            "indicators": indicators_ai_context(indicators),
        },
        asdict(regime),
        context.evidence,
    )
    return {
        "recommendation": recommendation,
        "scorePolicy": scoring_policy(candidates).as_dict(),
        "report": {**report.as_dict(), "dataGaps": [*context.news.data_gaps, *indicators["dataGaps"]]},
        "evidence": [asdict(e) for e in context.evidence],
        "providerAttempts": attempts,
        "newsSearch": context.news.as_dict(),
        "indicators": indicators,
        "valuationInputs": valuation_inputs(context.snapshot.as_dict()),
    }

"""HTML과 JSON 분석이 공유하는 시장·공시·뉴스 수집과 보고서 유스케이스."""

from dataclasses import asdict, dataclass, replace

from asgiref.sync import async_to_sync
from django.core.cache import cache

from research.analysis import Evidence, create_live_report, create_report
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
    news = collect_stock_news(snapshot.symbol, snapshot.company,
                              [e for e in evidence if e.kind == "news"],
                              yahoo_error="; ".join(errors), yahoo_cached=yahoo_cached)
    scores = score_snapshot(snapshot.as_dict(), sentiment_scores=news.sentiment_scores,
                            fundamentals=filing.fundamentals)
    return StockAnalysisContext(snapshot, scores,
                               [e for e in evidence if e.kind != "news"]
                               + list(filing.evidence) + news.evidence, news)


def analyze_live_stock(symbol: str) -> dict:
    context = collect_stock_context(symbol)
    snapshot = context.snapshot
    plan = trade_plan(snapshot.price, snapshot.atr_20 or 0.0, fetch_macro_regime().regime)
    report, attempts = create_live_report(
        snapshot.as_dict(), context.evidence,
        {**context.scores.as_ai_context(), "tradePlan": plan.as_dict() if plan else None,
         "newsSearch": context.news.as_dict()},
    )
    report = replace(report, data_gaps=list(dict.fromkeys(
        [*report.data_gaps, *context.news.data_gaps])))
    return {
        "result": {"snapshot": snapshot, "scores": context.scores, "report": report,
                   "trade_plan": plan, "news_search": context.news.as_dict(),
                   "chart": {"currency": snapshot.currency,
                             "points": [asdict(p) for p in snapshot.chart_points],
                             "tradePlan": plan.as_dict() if plan else None}},
        "evidence": context.evidence, "attempts": attempts,
    }


def analyze_ranked_stock(symbol, candidates, regime) -> dict | None:
    target = next((c for c in candidates if route_symbol(c.symbol).base ==
                   route_symbol(symbol).base), None)
    if target is None:
        return None
    context = collect_stock_context(target.symbol)
    # 호출자가 준 후보의 가격·재무 계약을 유지하고 대상 뉴스만 갱신한다.
    target = replace(target, news=context.scores.news,
                     news_observations=context.scores.news_observations)
    candidates = [target if c.symbol == target.symbol else c for c in candidates]
    recommendations = rank_candidates(candidates, regime, len(candidates))
    recommendation = next((r for r in recommendations if r["symbol"] == target.symbol), None)
    if recommendation is None:
        return None
    report, attempts = create_report(
        recommendation, {**asdict(target), "newsSearch": context.news.as_dict()},
        asdict(regime), context.evidence,
    )
    return {"recommendation": recommendation,
            "scorePolicy": scoring_policy(candidates).as_dict(),
            "report": {**report.as_dict(), "dataGaps": context.news.data_gaps},
            "evidence": [asdict(e) for e in context.evidence], "providerAttempts": attempts,
            "newsSearch": context.news.as_dict()}

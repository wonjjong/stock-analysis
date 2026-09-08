from dataclasses import dataclass
from math import exp
from statistics import mean, pstdev


@dataclass(frozen=True)
class Candidate:
    symbol: str
    price: float
    atr_20: float
    quality: float
    value: float
    momentum: float
    revisions: float
    news: float
    liquidity: float
    drawdown: float
    beta: float
    stale_ratio: float = 0.0
    news_observations: int = 0


@dataclass(frozen=True)
class MacroRegime:
    vix: float
    usdkrw_change_20d: float
    us10y_change_bp_20d: float
    credit_spread_change_bp_20d: float

    @property
    def risk_off(self) -> float:
        raw = (self.vix - 18) / 8 + max(self.usdkrw_change_20d, 0) / 6 + max(self.credit_spread_change_bp_20d, 0) / 40
        return max(0.0, min(1.0, 1 / (1 + exp(-raw)) - 0.35))


@dataclass(frozen=True)
class TradePlan:
    """현재 가격과 ATR로 계산한 기계적 진입·위험 관리 기준.

    종목의 매수 추천이 아니라, 분석자가 이미 매수 검토 중일 때 사용할 가격 기준이다.
    """

    entry_low: float
    entry_high: float
    stop: float
    target: float
    risk_off: float

    @property
    def risk_off_percent(self) -> float:
        return self.risk_off * 100

    def as_dict(self) -> dict[str, float]:
        return {
            "entryLow": round(self.entry_low, 2),
            "entryHigh": round(self.entry_high, 2),
            "stop": round(self.stop, 2),
            "target": round(self.target, 2),
            "riskOff": round(self.risk_off, 3),
        }


def trade_plan(price: float, atr_20: float, regime: MacroRegime) -> TradePlan | None:
    """랭킹과 개별 분석이 공통으로 쓰는 ATR 기반 가격 계획을 만든다."""
    if price <= 0 or atr_20 <= 0:
        return None
    risk_off = regime.risk_off
    risk_budget = max(.8, 1.8 - risk_off * .6)
    stop = price - atr_20 * risk_budget
    target = price + (price - stop) * max(1.6, 2.2 - risk_off * .4)
    return TradePlan(
        entry_low=price - atr_20 * .55,
        entry_high=price - atr_20 * .15,
        stop=stop,
        target=target,
        risk_off=risk_off,
    )


BASE_WEIGHTS = {"quality": .22, "value": .17, "momentum": .21, "revisions": .20, "news": .10, "risk": .10}
MIN_NEWS_COVERAGE_RATIO = 0.60


@dataclass(frozen=True)
class ScoringPolicy:
    """이번 비교군에 적용된 팩터 가용성 정책."""

    news_enabled: bool
    news_coverage_ratio: float

    @property
    def news_status(self) -> str:
        return "뉴스 반영" if self.news_enabled else "뉴스 데이터 축적 중 — 미반영"

    def as_dict(self) -> dict[str, float | bool | str]:
        return {
            "newsEnabled": self.news_enabled,
            "newsCoverageRatio": round(self.news_coverage_ratio, 3),
            "newsCoveragePercent": round(self.news_coverage_ratio * 100),
            "newsStatus": self.news_status,
        }


def _winsorized_z(values: list[float]) -> list[float]:
    if not values: return []
    ordered = sorted(values); lo = ordered[max(0, int(len(values) * .05) - 1)]; hi = ordered[min(len(values) - 1, int(len(values) * .95))]
    clipped = [min(hi, max(lo, value)) for value in values]
    sigma = pstdev(clipped)
    if sigma == 0: return [0.0] * len(values)
    center = mean(clipped)
    return [(value - center) / sigma for value in clipped]


def eligible_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """가격·유동성·시세 신선도라는 랭킹의 최소 기준을 통과한 후보만 남긴다."""
    return [c for c in candidates if c.price > 0 and c.liquidity >= 35 and c.stale_ratio <= .15]


def scoring_policy(candidates: list[Candidate]) -> ScoringPolicy:
    """뉴스가 충분히 쌓이기 전에는 뉴스 팩터를 점수에서 제외한다."""
    eligible = eligible_candidates(candidates)
    if not eligible:
        return ScoringPolicy(news_enabled=False, news_coverage_ratio=0.0)
    covered = sum(candidate.news_observations > 0 for candidate in eligible)
    coverage_ratio = covered / len(eligible)
    return ScoringPolicy(
        news_enabled=coverage_ratio >= MIN_NEWS_COVERAGE_RATIO,
        news_coverage_ratio=coverage_ratio,
    )


def rank_candidates(candidates: list[Candidate], regime: MacroRegime, limit: int = 5) -> list[dict]:
    """Point-in-time cross-sectional ranker. Inputs must only contain data available at the run timestamp."""
    eligible = eligible_candidates(candidates)
    if not eligible: return []
    policy = scoring_policy(eligible)
    factor_names = ("quality", "value", "momentum", "revisions")
    if policy.news_enabled:
        factor_names += ("news",)
    columns = {name: _winsorized_z([getattr(c, name) for c in eligible]) for name in factor_names}
    risk_off = regime.risk_off
    weights = BASE_WEIGHTS | {"quality": .22 + .07 * risk_off, "momentum": .21 - .05 * risk_off, "value": .17 + .03 * risk_off}
    if not policy.news_enabled:
        del weights["news"]
    ranked = []
    for i, c in enumerate(eligible):
        normalized = {name: 50 + 18 * columns[name][i] for name in columns}
        risk_score = max(0, 100 - c.drawdown * 1.8 - c.beta * 12 - risk_off * 18)
        raw = sum(normalized[name] * weights[name] for name in columns) + risk_score * weights["risk"]
        score = max(0, min(100, raw / sum(weights.values())))
        plan = trade_plan(c.price, c.atr_20, regime)
        if plan is None:
            continue
        action = "매수 유효" if score >= 72 and plan.target / c.price - 1 >= .08 else "관찰"
        news_confidence = 4 if c.news_observations > 0 else 0
        confidence = min(92, score * .72 + (1 - c.stale_ratio) * 16 + news_confidence)
        ranked.append(
            {
                "symbol": c.symbol,
                "score": round(score, 1),
                "confidence": round(confidence, 1),
                "action": action,
                "entry_low": round(plan.entry_low, 2),
                "entry_high": round(plan.entry_high, 2),
                "target": round(plan.target, 2),
                "stop": round(plan.stop, 2),
                "reasons": sorted(normalized, key=normalized.get, reverse=True)[:2],
            }
        )
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

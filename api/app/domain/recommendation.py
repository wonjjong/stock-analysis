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


BASE_WEIGHTS = {"quality": .22, "value": .17, "momentum": .21, "revisions": .20, "news": .10, "risk": .10}


def _winsorized_z(values: list[float]) -> list[float]:
    if not values: return []
    ordered = sorted(values); lo = ordered[max(0, int(len(values) * .05) - 1)]; hi = ordered[min(len(values) - 1, int(len(values) * .95))]
    clipped = [min(hi, max(lo, value)) for value in values]
    sigma = pstdev(clipped)
    if sigma == 0: return [0.0] * len(values)
    center = mean(clipped)
    return [(value - center) / sigma for value in clipped]


def rank_candidates(candidates: list[Candidate], regime: MacroRegime, limit: int = 5) -> list[dict]:
    """Point-in-time cross-sectional ranker. Inputs must only contain data available at the run timestamp."""
    eligible = [c for c in candidates if c.price > 0 and c.liquidity >= 35 and c.stale_ratio <= .15]
    if not eligible: return []
    columns = {name: _winsorized_z([getattr(c, name) for c in eligible]) for name in ("quality", "value", "momentum", "revisions", "news")}
    risk_off = regime.risk_off
    weights = BASE_WEIGHTS | {"quality": .22 + .07 * risk_off, "momentum": .21 - .05 * risk_off, "value": .17 + .03 * risk_off}
    ranked = []
    for i, c in enumerate(eligible):
        normalized = {name: 50 + 18 * columns[name][i] for name in columns}
        risk_score = max(0, 100 - c.drawdown * 1.8 - c.beta * 12 - risk_off * 18)
        raw = sum(normalized[name] * weights[name] for name in columns) + risk_score * weights["risk"]
        score = max(0, min(100, raw / sum(weights.values())))
        risk_budget = max(.8, 1.8 - risk_off * .6)
        stop = c.price - c.atr_20 * risk_budget
        target = c.price + (c.price - stop) * max(1.6, 2.2 - risk_off * .4)
        action = "매수 유효" if score >= 72 and target / c.price - 1 >= .08 else "관찰"
        confidence = min(92, score * .72 + (1 - c.stale_ratio) * 20)
        ranked.append({"symbol": c.symbol, "score": round(score, 1), "confidence": round(confidence, 1), "action": action, "entry_low": round(c.price - c.atr_20 * .55, 2), "entry_high": round(c.price - c.atr_20 * .15, 2), "target": round(target, 2), "stop": round(stop, 2), "reasons": sorted(normalized, key=normalized.get, reverse=True)[:2]})
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

"""시장 스냅샷을 rank_candidates 가 먹는 0~100 팩터 점수로 바꾼다.

## 왜 이 파일이 필요한가
recommendation.rank_candidates 는 **점수를 매기는 코드가 아니라 이미 매겨진 점수로 줄을
세우는 코드**다. quality=82 같은 값이 어디서 오는지는 그쪽 관심사가 아니라서, 이 변환이
없으면 API 를 호출하는 쪽이 팩터 점수를 손으로 만들어 넣어야 한다.

## 결측치는 중립 처리하고 커버리지를 남긴다
공개 데이터는 종목마다 빠지는 항목이 다르다. 없는 값을 0 으로 치면 그 종목이 부당하게
바닥으로 가고, 조용히 빼면 다른 종목과 비교가 안 된다. 그래서 없는 값은 중립(50)으로 두되
'몇 개나 실제 데이터로 채웠는지'를 coverage 로 남겨, 근거가 얇은 종목을 걸러낼 수 있게 한다.

## 통화를 환산하지 않는다
거래대금은 원화와 달러가 1,000배 넘게 차이 난다. 환율 소스가 없으므로 통화별 기준선을
따로 두고 점수만 비교 가능하게 만든다. 환율을 지어내 환산하지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from research.recommendation import Candidate

NEUTRAL = 50.0

# (원시값, 점수) 구간점. 사이는 선형 보간하고 양 끝은 잘라낸다.
type Curve = tuple[tuple[float, float], ...]

MOMENTUM_CURVES: dict[str, Curve] = {
    "return_1m_pct": ((-20, 0), (0, 50), (20, 100)),
    "return_6m_pct": ((-40, 0), (0, 50), (50, 100)),
    "return_1y_pct": ((-50, 0), (0, 50), (100, 100)),
    # 52주 고점과의 거리. 0 에 가까울수록 강세다.
    "distance_from_high_pct": ((-60, 0), (-20, 50), (0, 100)),
}

# 저평가일수록 높은 점수라 곡선이 우하향이다.
VALUE_CURVES: dict[str, Curve] = {
    "trailing_pe": ((5, 100), (15, 70), (30, 40), (60, 0)),
    "price_to_book": ((0.5, 100), (1.5, 70), (4, 40), (10, 0)),
}

QUALITY_CURVES: dict[str, Curve] = {
    "gross_margin_pct": ((0, 0), (20, 50), (50, 100)),
    "profit_margin_pct": ((-20, 0), (0, 50), (25, 100)),
    "revenue_growth_pct": ((-20, 0), (0, 50), (30, 100)),
}

# 20일 평균 거래대금 기준선. 통화마다 자릿수가 달라 따로 둔다.
LIQUIDITY_CURVES: dict[str, Curve] = {
    "KRW": ((1e8, 0), (1e9, 40), (1e10, 70), (1e11, 100)),
    "USD": ((1e5, 0), (1e6, 40), (1e7, 70), (1e8, 100)),
}
DEFAULT_LIQUIDITY_CURRENCY = "USD"

# stale_ratio 는 **시세 데이터가 얼마나 비었는지**만 센다.
#
# 재무 지표까지 세면 안 된다. yfinance 는 한국 종목의 PER·PBR 을 주지 않는데, 그걸 결측으로
# 세면 rank_candidates 의 stale_ratio <= 0.15 필터에 코스피 종목이 전부 걸려 순위에서
# 조용히 사라진다(실제로 그랬다). 재무가 얼마나 채워졌는지는 coverage 로 따로 보여 준다.
#
# 아래 항목은 상장 종목이면 가격 이력만으로 계산되므로, 비어 있다면 정말로 데이터가 부실한
# 것이다.
CORE_INPUTS = (
    "price",
    "return_1m_pct",
    "return_6m_pct",
    "return_1y_pct",
    "avg_volume_20d",
    "volatility_20d_pct",
    "max_drawdown_1y_pct",
)


@dataclass(frozen=True, slots=True)
class FactorScores:
    """rank_candidates 입력 한 벌과, 그 값이 얼마나 실제 데이터로 채워졌는지."""

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
    stale_ratio: float
    coverage: dict[str, int] = field(default_factory=dict)

    def as_candidate(self) -> Candidate:
        return Candidate(
            symbol=self.symbol,
            price=self.price,
            atr_20=self.atr_20,
            quality=self.quality,
            value=self.value,
            momentum=self.momentum,
            revisions=self.revisions,
            news=self.news,
            liquidity=self.liquidity,
            drawdown=self.drawdown,
            beta=self.beta,
            stale_ratio=self.stale_ratio,
        )


def _number(value: object) -> float | None:
    """유한한 실수만 통과시킨다. None·NaN·inf 는 결측으로 본다."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def interpolate(value: float, curve: Curve) -> float:
    """구간점 사이를 선형 보간한다. 곡선 밖은 양 끝 점수로 자른다."""
    if value <= curve[0][0]:
        return curve[0][1]
    if value >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in pairwise(curve):
        if x0 <= value <= x1:
            span = x1 - x0
            return y0 if span == 0 else y0 + (y1 - y0) * (value - x0) / span
    return NEUTRAL


def _factor(snapshot: dict[str, Any], curves: dict[str, Curve]) -> tuple[float, int]:
    """여러 지표의 평균 점수와 실제로 채워진 지표 수를 낸다."""
    scores = [
        interpolate(number, curve)
        for name, curve in curves.items()
        if (number := _number(snapshot.get(name))) is not None
    ]
    if not scores:
        return NEUTRAL, 0
    return sum(scores) / len(scores), len(scores)


def _liquidity(snapshot: dict[str, Any]) -> tuple[float, int]:
    """20일 평균 거래대금을 통화별 기준선으로 점수화한다."""
    volume = _number(snapshot.get("avg_volume_20d"))
    price = _number(snapshot.get("price"))
    if volume is None or price is None or price <= 0:
        return NEUTRAL, 0
    currency = str(snapshot.get("currency") or "").upper()
    curve = LIQUIDITY_CURVES.get(currency, LIQUIDITY_CURVES[DEFAULT_LIQUIDITY_CURRENCY])
    return interpolate(volume * price, curve), 1


def news_score(sentiment_scores: list[int]) -> tuple[float, int]:
    """뉴스 감성 점수(0~100)의 평균. 기사가 없으면 중립이다.

    NewsInsight.sentiment_score 가 이미 0~100 척도라 그대로 평균 낸다.
    """
    usable = [float(score) for score in sentiment_scores if _number(score) is not None]
    if not usable:
        return NEUTRAL, 0
    return sum(usable) / len(usable), len(usable)


def score_snapshot(
    snapshot: dict[str, Any],
    *,
    sentiment_scores: list[int] | None = None,
) -> FactorScores:
    """MarketSnapshot dict 를 팩터 점수 한 벌로 바꾼다.

    revisions(애널리스트 추정치 변화)는 공개 소스가 없어 항상 중립이다. rank_candidates 가
    횡단면 z-score 를 쓰므로, 모든 종목이 같은 값이면 기여가 0 이 되어 자연히 빠진다.
    """
    momentum, momentum_filled = _factor(snapshot, MOMENTUM_CURVES)
    value, value_filled = _factor(snapshot, VALUE_CURVES)
    quality, quality_filled = _factor(snapshot, QUALITY_CURVES)
    liquidity, liquidity_filled = _liquidity(snapshot)
    news, news_filled = news_score(sentiment_scores or [])

    # rank_candidates 는 drawdown 을 '클수록 나쁨'인 양수로 받는다.
    # 스냅샷의 max_drawdown_1y_pct 는 음수라 부호를 뒤집는다.
    raw_drawdown = _number(snapshot.get("max_drawdown_1y_pct"))
    drawdown = abs(raw_drawdown) if raw_drawdown is not None else 0.0

    filled = sum(1 for name in CORE_INPUTS if _number(snapshot.get(name)) is not None)
    stale_ratio = 1 - filled / len(CORE_INPUTS)

    return FactorScores(
        symbol=str(snapshot.get("symbol") or ""),
        price=_number(snapshot.get("price")) or 0.0,
        atr_20=_number(snapshot.get("atr_20")) or 0.0,
        quality=quality,
        value=value,
        momentum=momentum,
        revisions=NEUTRAL,
        news=news,
        liquidity=liquidity,
        drawdown=drawdown,
        beta=_number(snapshot.get("beta")) or 1.0,
        stale_ratio=stale_ratio,
        coverage={
            "momentum": momentum_filled,
            "value": value_filled,
            "quality": quality_filled,
            "liquidity": liquidity_filled,
            "news": news_filled,
            "revisions": 0,
        },
    )

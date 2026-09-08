"""외부 재무제표를 정량 팩터가 소비하는 값으로 표현한다.

이 모듈은 DART·SEC·시세 공급자의 응답 형식을 알지 않는다. 각 어댑터는 자신이 읽은
재무제표를 이 값 객체로 변환하고, 스코어러는 이 값만 받아 기존 시장 스냅샷을 보완한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FundamentalMetrics:
    """재무제표 기준으로 계산한 가치·퀄리티 팩터 입력값."""

    source: str
    period: str
    trailing_pe: float | None = None
    price_to_book: float | None = None
    profit_margin_pct: float | None = None
    revenue_growth_pct: float | None = None

    def score_inputs(self) -> dict[str, float]:
        """실제로 계산된 값만 돌려줘 결측값은 기존 보조 공급자가 보완하게 한다."""
        return {
            name: value
            for name, value in {
                "trailing_pe": self.trailing_pe,
                "price_to_book": self.price_to_book,
                "profit_margin_pct": self.profit_margin_pct,
                "revenue_growth_pct": self.revenue_growth_pct,
            }.items()
            if value is not None
        }

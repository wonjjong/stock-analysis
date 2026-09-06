"""rank_candidates 가 쓰는 시장 국면(MacroRegime)을 공개 데이터로 만든다.

## 신용스프레드는 채우지 않는다
MacroRegime 은 하이일드 스프레드 변화를 받지만 무료로 얻을 수 있는 소스가 없다(FRED 의
BAMLH0A0HYM2 는 yfinance 에 없다). 값을 지어내면 risk_off 가 조용히 틀리므로 0(변화 없음)
으로 두고, 화면에 '미반영'을 표시한다. 나중에 FRED API 키가 생기면 여기만 채우면 된다.

## 실패해도 분석을 막지 않는다
지표를 못 받으면 중립 국면을 쓴다. 거시 지표가 없다고 종목 랭킹 자체가 불가능해지는 것은
과한 결합이다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import yfinance as yf

from research.recommendation import MacroRegime

logger = logging.getLogger(__name__)

# VIX 장기 중앙값 근처. 지표를 못 받았을 때 risk_off 가 0 에 가깝도록 잡는다.
NEUTRAL_VIX = 18.0
LOOKBACK_SESSIONS = 20


@dataclass(frozen=True, slots=True)
class MacroReading:
    """국면 지표 한 벌과, 무엇을 실제로 받았는지."""

    regime: MacroRegime
    sources: dict[str, bool]

    @property
    def complete(self) -> bool:
        return all(self.sources.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "vix": self.regime.vix,
            "usdkrw_change_20d": self.regime.usdkrw_change_20d,
            "us10y_change_bp_20d": self.regime.us10y_change_bp_20d,
            "credit_spread_change_bp_20d": self.regime.credit_spread_change_bp_20d,
            "risk_off": round(self.regime.risk_off, 3),
            "sources": dict(self.sources),
        }


def _closes(symbol: str) -> list[float] | None:
    try:
        history = yf.Ticker(symbol).history(period="3mo", interval="1d", timeout=15)
    except Exception as reason:  # 공급자가 어떤 예외든 던질 수 있다
        logger.info("거시 지표 %s 조회 실패: %s", symbol, reason)
        return None
    if history.empty or "Close" not in history:
        return None
    values = [float(v) for v in history["Close"].dropna() if math.isfinite(float(v))]
    return values or None


def _pct_change(values: list[float] | None, sessions: int = LOOKBACK_SESSIONS) -> float | None:
    if values is None or len(values) <= sessions or values[-sessions - 1] == 0:
        return None
    return (values[-1] / values[-sessions - 1] - 1) * 100


def fetch_macro_regime() -> MacroReading:
    """VIX·원달러·미국 10년물로 국면을 만든다. 못 받은 지표는 중립으로 둔다."""
    vix_closes = _closes("^VIX")
    vix = vix_closes[-1] if vix_closes else NEUTRAL_VIX

    usdkrw_change = _pct_change(_closes("KRW=X"))

    # ^TNX 는 10년물 금리를 퍼센트로 준다. bp 변화는 (현재-과거)*100 이다.
    tnx = _closes("^TNX")
    us10y_change_bp = None
    if tnx is not None and len(tnx) > LOOKBACK_SESSIONS:
        us10y_change_bp = (tnx[-1] - tnx[-LOOKBACK_SESSIONS - 1]) * 100

    return MacroReading(
        regime=MacroRegime(
            vix=vix,
            usdkrw_change_20d=usdkrw_change or 0.0,
            us10y_change_bp_20d=us10y_change_bp or 0.0,
            credit_spread_change_bp_20d=0.0,
        ),
        sources={
            "vix": vix_closes is not None,
            "usdkrw": usdkrw_change is not None,
            "us10y": us10y_change_bp is not None,
            # 무료 소스가 없어 항상 미반영이다.
            "credit_spread": False,
        },
    )

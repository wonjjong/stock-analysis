"""티커 표기에서 시장을 판별한다. yfinance 접미사 규약이 기준이다.

한국 종목은 yfinance 에서 005930.KS(코스피) / 035720.KQ(코스닥) 로 표기된다. 사용자가
접미사 없이 '005930' 만 넣는 경우가 많아, 시세 조회는 두 접미사를 차례로 시도한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 코스피 .KS, 코스닥 .KQ. 미국 티커에는 이런 접미사가 없다.
KR_SUFFIXES = ("KS", "KQ")
_KR_CODE = re.compile(r"^\d{6}$")


@dataclass(frozen=True, slots=True)
class SymbolRoute:
    """시세·공시 조회에 필요한 최소 정보."""

    symbol: str  # 사용자가 넣은 원형
    base: str  # 거래소 접미사를 뗀 표기(005930, IREN)
    market: str  # "KR" | "US"


def route_symbol(symbol: str) -> SymbolRoute:
    """'005930.KS' → KR/005930, '005930' → KR/005930, 'IREN' → US/IREN."""
    normalized = "".join(symbol.split()).upper()
    head, _, suffix = normalized.rpartition(".")
    if head and suffix in KR_SUFFIXES:
        return SymbolRoute(symbol=normalized, base=head, market="KR")
    if _KR_CODE.match(normalized):
        return SymbolRoute(symbol=normalized, base=normalized, market="KR")
    return SymbolRoute(symbol=normalized, base=normalized, market="US")


def yfinance_candidates(route: SymbolRoute) -> tuple[str, ...]:
    """yfinance 조회 후보를 우선순위대로 낸다. 접미사 없는 한국 종목은 KS→KQ 순서."""
    if route.market != "KR" or route.symbol != route.base:
        return (route.symbol,)
    return tuple(f"{route.base}.{suffix}" for suffix in KR_SUFFIXES)

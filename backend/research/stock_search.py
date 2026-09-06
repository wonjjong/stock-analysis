"""종목 분석 화면의 검색 자동완성.

국내는 KIS 종목마스터, 미국은 SEC 등록 티커 목록을 본다. 둘 다 인증이 필요 없는 파일이라
자격증명 없이 동작한다.

## 왜 검색 결과에 거래소 접미사를 붙여 주는가
사용자가 '삼성전자' 를 고르면 분석 폼에는 005930 이 아니라 **005930.KS** 가 들어가야 한다.
접미사가 없으면 market_data 가 .KS 와 .KQ 를 차례로 시도하며 헛도는데, 종목마스터가 이미
거래소를 알고 있으므로 여기서 확정해 준다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research.services.company_index import CompanyIndexError, CompanyRef
from research.services.kis_index import kis_index
from research.services.sec_index import sec_index

# yfinance 거래소 접미사.
YF_SUFFIX = {"KOSPI": "KS", "KOSDAQ": "KQ"}
DEFAULT_LIMIT = 8


@dataclass(frozen=True, slots=True)
class StockChoice:
    """검색 결과 한 건. symbol 을 그대로 분석 폼에 넣으면 된다."""

    symbol: str
    code: str
    name: str
    market: str
    exchange: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _kr_choice(ref: CompanyRef) -> StockChoice:
    suffix = YF_SUFFIX.get(ref.exchange, "KS")
    return StockChoice(
        symbol=f"{ref.ticker}.{suffix}",
        code=ref.ticker,
        name=ref.name,
        market="KR",
        exchange=ref.exchange,
    )


def _us_choice(ref: CompanyRef) -> StockChoice:
    return StockChoice(
        symbol=ref.ticker,
        code=ref.ticker,
        name=ref.name,
        market="US",
        exchange=ref.exchange or "US",
    )


def search_symbols(query: str, limit: int = DEFAULT_LIMIT) -> list[StockChoice]:
    """국내·미국 종목을 함께 검색한다. 한쪽 인덱스가 실패해도 다른 쪽 결과는 돌려준다.

    검색은 분석의 전 단계일 뿐이라, 인덱스 하나가 죽었다고 화면을 막지 않는다.
    """
    cleaned = query.strip()
    if len(cleaned) < 1:
        return []

    half = max(1, limit // 2)
    results: list[StockChoice] = []
    for index, build, share in ((kis_index, _kr_choice, limit), (sec_index, _us_choice, half)):
        try:
            results.extend(build(ref) for ref in index.autocomplete(cleaned, share))
        except CompanyIndexError:
            continue

    # 국내를 먼저 보여 주되, 전체 개수는 limit 을 넘기지 않는다.
    return results[:limit]

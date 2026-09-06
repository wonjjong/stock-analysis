"""검색 결과 → 분석 폼 입력값 변환 검증."""

from __future__ import annotations

from research.services.company_index import CompanyRef
from research.stock_search import _kr_choice, _us_choice


def _ref(**kwargs) -> CompanyRef:
    base = {"market": "KR", "key": "005930", "ticker": "005930", "name": "삼성전자"}
    return CompanyRef(**{**base, **kwargs})


def test_kospi_choice_gets_the_ks_suffix():
    """폼에는 005930 이 아니라 005930.KS 가 들어가야 yfinance 가 한 번에 맞춘다."""
    assert _kr_choice(_ref(exchange="KOSPI")).symbol == "005930.KS"


def test_kosdaq_choice_gets_the_kq_suffix():
    choice = _kr_choice(_ref(key="086520", ticker="086520", name="에코프로", exchange="KOSDAQ"))
    assert choice.symbol == "086520.KQ"


def test_unknown_exchange_falls_back_to_kospi():
    assert _kr_choice(_ref()).symbol == "005930.KS"


def test_us_choice_uses_the_bare_ticker():
    choice = _us_choice(_ref(market="US", key="0001878848", ticker="IREN", name="IREN Ltd"))
    assert (choice.symbol, choice.market) == ("IREN", "US")

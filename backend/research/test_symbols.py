"""티커 표기 → 시장 판별 검증."""

from __future__ import annotations

from research.symbols import route_symbol, yfinance_candidates


def test_kospi_suffix_is_recognised_as_korean():
    route = route_symbol("005930.KS")
    assert (route.market, route.base) == ("KR", "005930")


def test_bare_six_digit_code_is_korean_because_us_tickers_are_not_numeric():
    assert route_symbol("005930").market == "KR"


def test_plain_ticker_is_us():
    route = route_symbol(" iren ")
    assert (route.market, route.symbol) == ("US", "IREN")


def test_class_share_dot_is_not_mistaken_for_an_exchange_suffix():
    assert route_symbol("BRK.B").market == "US"


def test_bare_korean_code_tries_kospi_then_kosdaq():
    assert yfinance_candidates(route_symbol("005930")) == ("005930.KS", "005930.KQ")


def test_explicit_suffix_is_used_as_is():
    assert yfinance_candidates(route_symbol("035720.KQ")) == ("035720.KQ",)

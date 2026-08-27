"""종목 매칭·키워드 동일성."""

from __future__ import annotations

from news.crawler.keywords import extract_keywords
from news.crawler.symbols import lookup_symbol, match_symbols, occurrences


def test_symbol_cases_match(parity: dict) -> None:
    problems: list[str] = []
    for case in parity["symbols"]:
        expected = case["matches"]
        actual = [m.as_dict() for m in match_symbols("", case["text"])]
        if actual != expected:
            problems.append(
                f"  {case['text'][:34]}…\n    기대 {expected!r}\n    실제 {actual!r}"
            )
    assert not problems, "종목 매칭 불일치 {}건:\n{}".format(len(problems), "\n".join(problems))


def test_keyword_cases_match(parity: dict) -> None:
    for case in parity["keywords"]:
        actual = extract_keywords(case["title"], case["body"])
        assert actual == case["keywords"], f"제목 {case['title'][:24]}…"


def test_longer_alias_wins() -> None:
    """카카오뱅크 기사가 카카오로 중복 집계되지 않는다."""
    matches = {m.symbol: m for m in match_symbols("", "카카오뱅크 실적이 개선됐다.")}
    assert "323410" in matches          # 카카오뱅크
    assert "035720" not in matches      # 카카오


def test_share_button_noise_is_not_a_symbol() -> None:
    assert match_symbols("", "카카오톡으로 공유하기 · 네이버 블로그에 담기") == []


def test_latin_ticker_requires_word_boundary() -> None:
    """ARM 이 alarm 에 걸리지 않는다."""
    assert occurrences("an alarm went off", "ARM") == 0
    assert occurrences("ARM shares rose", "ARM") == 1


def test_lookup_symbol() -> None:
    assert lookup_symbol("005930").name == "삼성전자"
    assert lookup_symbol("삼성전자").symbol == "005930"
    assert lookup_symbol("하이닉스").symbol == "000660"
    assert lookup_symbol("없는종목") is None

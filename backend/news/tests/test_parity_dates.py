"""
날짜 판독 동일성. 정답지(`tests/parity/expected.json`)의 43개 사례를 그대로 돌린다.

정답지는 동결된 TypeScript 구현이 낸 출력이다. 값이 하나라도 다르면 실패한다 — 특히
`None` 이어야 하는 입력이 숫자를 내면 기사 번호가 발행일로 둔갑한 것이고, 반대로 숫자여야
하는 입력이 `None` 을 내면 기사가 조용히 버려진다.
"""

from __future__ import annotations

import pytest

from news.crawler.dates import date_kst, parse_visible_date


def _cases(parity: dict, group: str) -> list:
    return parity[group]


def test_all_date_cases_match(parity: dict, now_ms: int) -> None:
    mismatches: list[str] = []
    for case in _cases(parity, "dates"):
        expected = case["parseVisibleDate"]
        actual = parse_visible_date(case["input"], now_ms)
        if actual != expected:
            mismatches.append(
                f"  {case['input']!r}\n    기대 {expected!r}\n    실제 {actual!r}"
            )
    assert not mismatches, "날짜 판독 불일치 {}건:\n{}".format(
        len(mismatches), "\n".join(mismatches)
    )


@pytest.mark.parametrize(
    "text",
    [
        "경기 결과 3-2 완승",
        "기사 번호 AKR20260827173200001",
        "조회수 1,234",
        "1-0",
        "부산 2-1 승리",
        "12",
        "12-3",
        "2026",
        "댓글 5",
        "",
        "   ",
    ],
)
def test_non_dates_are_rejected(text: str, now_ms: int) -> None:
    """날짜가 아닌 것을 날짜로 읽지 않는다. dateutil 을 쓰면 여기서 무너진다."""
    assert parse_visible_date(text, now_ms) is None


def test_ascii_digits_only(now_ms: int) -> None:
    """
    Python 의 `\\d` 는 유니코드라 전각 숫자까지 매치한다. JS 는 ASCII 전용이므로
    전각 입력은 원본에서 날짜가 아니다.
    """
    assert parse_visible_date("２０２６-０８-２７ １８:１８", now_ms) is None
    assert parse_visible_date("０８-２７ １８:１８", now_ms) is None


def test_js_date_utc_overflow_is_reproduced(now_ms: int) -> None:
    """
    원본의 가드는 일(day)을 1~31 로만 보므로 2월 30일이 통과한 뒤 JS `Date.UTC` 가
    3월 2일로 정규화한다. Python `datetime` 은 그대로 만들면 예외를 던지므로,
    `timedelta` 누산으로 같은 결과를 낸다.
    """
    result = parse_visible_date("2026-02-30 10:00", now_ms)
    assert result is not None
    assert date_kst(result) == "2026-03-02"


def test_all_date_kst_cases_match(parity: dict) -> None:
    for case in _cases(parity, "dateKst"):
        assert date_kst(case["input"]) == case["dateKst"], f"입력 {case['input']}"

"""
URL 정규화 동일성.

`canonical_url` 이 조금이라도 다르게 정규화되면 다음 수집이 기존 기사를 유사 URL 로
재삽입하고 UNIQUE 인덱스가 중복으로 보지 못한다. 코퍼스가 조용히 두 배가 되므로 이
테스트가 이식 전체에서 두 번째로 중요하다.
"""

from __future__ import annotations

import pytest

from news.crawler.jsurl import (
    InvalidSourceUrl,
    absolute_article_url,
    is_private_ipv4,
    page_number,
    validate_source_url,
)

BASE = "https://news.example.com/news"


def test_article_url_cases_match(parity: dict) -> None:
    """정답지는 parseNewsPage 를 통해 관찰한 값이라, 항목이 하나인 경우만 직접 비교한다."""
    mismatches: list[str] = []
    for case in parity["urlsViaAnchors"]:
        items = case["items"]
        if not isinstance(items, list) or len(items) != 1:
            continue
        expected = items[0]
        actual = absolute_article_url(case["href"], BASE)
        if actual != expected:
            mismatches.append(f"  {case['href']!r}\n    기대 {expected!r}\n    실제 {actual!r}")
    assert not mismatches, "URL 정규화 불일치 {}건:\n{}".format(
        len(mismatches), "\n".join(mismatches)
    )


def test_source_url_cases_match(parity: dict) -> None:
    mismatches: list[str] = []
    for case in parity["sourceUrls"]:
        expected = case["validateSourceUrl"]
        expected_error = expected.get("__error") if isinstance(expected, dict) else None
        try:
            actual: str | None = validate_source_url(case["input"])
            actual_error = None
        except InvalidSourceUrl as reason:
            actual, actual_error = None, str(reason)

        if expected_error is not None:
            if actual_error != expected_error:
                mismatches.append(
                    f"  {case['input']!r}\n    기대 오류 {expected_error!r}\n"
                    f"    실제 {actual_error!r} / 값 {actual!r}"
                )
        elif actual != expected:
            mismatches.append(f"  {case['input']!r}\n    기대 {expected!r}\n    실제 {actual!r}")

    assert not mismatches, "소스 URL 검증 불일치 {}건:\n{}".format(
        len(mismatches), "\n".join(mismatches)
    )


def test_page_number_cases_match(parity: dict) -> None:
    for case in parity["pagination"]:
        assert page_number(case["url"]) == case["pageNumber"], f"입력 {case['url']}"


@pytest.mark.parametrize(
    ("host", "private"),
    [
        ("10.0.0.1", True), ("127.0.0.1", True), ("0.0.0.0", True),
        ("169.254.169.254", True), ("172.16.0.1", True), ("172.31.255.255", True),
        ("192.168.1.1", True), ("224.0.0.1", True), ("255.255.255.255", True),
        ("1.1.1.1", False), ("8.8.8.8", False), ("172.15.0.1", False),
        ("172.32.0.1", False), ("news.example.com", False), ("999.1.1.1", True),
    ],
)
def test_private_ipv4(host: str, private: bool) -> None:
    assert is_private_ipv4(host) is private


def test_tracking_params_are_stripped_but_others_kept() -> None:
    """추적 쿼리만 떼고 나머지는 남긴다. 이 목록이 영구 계약이다."""
    assert absolute_article_url("/v/1?utm_source=a&keep=1", BASE) == (
        "https://news.example.com/v/1?keep=1"
    )
    assert absolute_article_url("/v/1?section=x&cp=y&ref=z", BASE) == (
        "https://news.example.com/v/1"
    )


def test_empty_question_mark_is_preserved() -> None:
    """
    원래 비어 있던 `?` 는 남지만, 파라미터가 전부 삭제되어 비면 `?` 가 사라진다.
    WHATWG 의 이 비대칭을 그대로 따라야 dedup 키가 일치한다.
    """
    assert absolute_article_url("/v/1?", BASE) == "https://news.example.com/v/1?"
    assert absolute_article_url("/v/1?utm_source=a", BASE) == "https://news.example.com/v/1"

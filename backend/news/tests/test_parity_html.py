"""
HTML·피드 파싱 동일성. 픽스처 결과를 항목 단위로 비교한다.

제목·URL·excerpt·발행시각·**순서**까지 일치해야 한다. 순서가 다르면 dedup 이 다른 항목을
남기고, excerpt 가 다르면 content_hash 가 달라진다.
"""

from __future__ import annotations

from pathlib import Path

from news.crawler.feed import looks_like_feed, parse_feed
from news.crawler.html import find_next_page_url, parse_news_page

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LIST_URL = "https://news.example.com/news"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _diff(actual: list[dict], expected: list[dict]) -> list[str]:
    problems: list[str] = []
    if len(actual) != len(expected):
        problems.append(f"항목 수: 실제 {len(actual)} / 기대 {len(expected)}")
    for index, (got, want) in enumerate(zip(actual, expected, strict=False)):
        for key in ("title", "url", "excerpt", "publishedAt"):
            if got[key] != want[key]:
                problems.append(
                    f"[{index}] {key}\n    기대 {want[key]!r}\n    실제 {got[key]!r}"
                )
    return problems


def test_feed_fixture_matches(parity: dict, now_ms: int) -> None:
    items = parse_feed(_fixture("news-feed.xml"), "https://news.example.com/rss", now_ms)
    problems = _diff([i.as_dict() for i in items], parity["feedFixture"])
    assert not problems, "RSS 파싱 불일치:\n" + "\n".join(problems)


def test_html_fixture_matches(parity: dict, now_ms: int) -> None:
    items = parse_news_page(_fixture("news-list.html"), LIST_URL, now_ms)
    problems = _diff([i.as_dict() for i in items], parity["htmlFixture"]["items"])
    assert not problems, "HTML 파싱 불일치:\n" + "\n".join(problems)


def test_next_page_matches(parity: dict) -> None:
    actual = find_next_page_url(_fixture("news-list.html"), LIST_URL)
    assert actual == parity["htmlFixture"]["nextPage"]


def test_looks_like_feed() -> None:
    assert looks_like_feed(_fixture("news-feed.xml"))
    assert not looks_like_feed(_fixture("news-list.html"))


def test_live_feed_fixture_matches(parity: dict, now_ms: int) -> None:
    """
    실제 언론사 피드 90KB 를 두 구현에 돌려 비교한 결과를 고정한 것.

    픽스처 2개(합성 8건)만으로는 부족하다 — 실제 피드에는 다양한 날짜 형식과 HTML 엔티티,
    CDATA 가 섞여 있고 조용한 과소수집은 거기서 발생한다.
    """
    live = parity.get("liveFeedFixture")
    if not live:
        import pytest

        pytest.skip("라이브 피드 정답지가 없습니다. scripts/harvest-parity.mjs 참고.")

    path = FIXTURES.parent / "parity" / live["file"]
    if not path.is_file():
        import pytest

        pytest.skip(f"{path} 가 없습니다.")

    items = parse_feed(path.read_text(encoding="utf-8"), live["url"], now_ms)
    problems = _diff([i.as_dict() for i in items], live["items"])
    assert not problems, "라이브 피드 파싱 불일치:\n" + "\n".join(problems[:20])

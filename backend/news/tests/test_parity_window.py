"""수집 창 동일성. 경계값이 핵심이다 — 정확히 창 끝, 정확히 시계오차 끝."""

from __future__ import annotations

from news.crawler.types import FeedItem
from news.crawler.window import (
    CLOCK_SKEW_MS,
    DEFAULT_WINDOW_HOURS,
    clamp_window_hours,
    select_recent_items,
)

HOUR_MS = 60 * 60 * 1000


def test_clamp_cases_match(parity: dict) -> None:
    for case in parity["clampWindowHours"]:
        raw = case["input"]
        value = float("nan") if raw == "NaN" else float("inf") if raw == "Infinity" else raw
        assert clamp_window_hours(value) == case["clamped"], f"입력 {raw!r}"


def test_window_cases_match(parity: dict, now_ms: int) -> None:
    for case in parity["window"]:
        items = [FeedItem("t", "u", "e", now_ms + case["offsetHours"] * HOUR_MS)]
        kept = len(select_recent_items(items, now_ms, case["hours"]))
        assert kept == case["kept"], f"창 {case['hours']}h, 오프셋 {case['offsetHours']}h"


def test_boundaries_are_inclusive(now_ms: int) -> None:
    """창 시작과 시계오차 끝은 포함, 그 한 밀리초 밖은 제외."""
    window = DEFAULT_WINDOW_HOURS * HOUR_MS
    cases = {
        now_ms - window: 1,          # 정확히 창 시작 → 포함
        now_ms - window - 1: 0,      # 1ms 이전 → 제외
        now_ms + CLOCK_SKEW_MS: 1,   # 정확히 시계오차 끝 → 포함
        now_ms + CLOCK_SKEW_MS + 1: 0,
    }
    for published, expected in cases.items():
        items = [FeedItem("t", "u", "e", published)]
        assert len(select_recent_items(items, now_ms)) == expected, f"published={published}"


def test_missing_date_is_dropped(now_ms: int) -> None:
    """날짜를 못 읽은 기사는 버린다. 이 동작이 조용한 과소수집의 원인이므로 명시한다."""
    assert select_recent_items([FeedItem("t", "u", "e", None)], now_ms) == []

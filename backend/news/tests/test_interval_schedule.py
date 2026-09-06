"""
주기(interval) 기반 스케줄. 이식 대상이 아니라 이 저장소에서 새로 만든 동작이므로
정답지가 아니라 직접 단정한다.
"""

from datetime import UTC, datetime

import pytest

from news.crawler.schedule import (
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    clamp_interval_minutes,
    next_interval_run_at,
)


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp() * 1000)


def test_clamp_rejects_non_positive_and_garbage() -> None:
    """0 은 '주기 없음'이다. 하루 한 번 동작으로 떨어져야 한다."""
    for value in (0, -1, -999, None, float("nan"), float("inf")):
        assert clamp_interval_minutes(value) == 0


def test_clamp_pins_to_bounds() -> None:
    assert clamp_interval_minutes(1) == MIN_INTERVAL_MINUTES
    assert clamp_interval_minutes(30) == 30
    assert clamp_interval_minutes(99999) == MAX_INTERVAL_MINUTES


def test_thirty_minute_cadence_lands_on_the_half_hour() -> None:
    """
    사용자가 기대하는 동작: 12:05 에 돌면 다음은 12:30, 12:30 에 돌면 다음은 13:00.
    `now + 30분` 이 아니라 경계이므로 실행이 늦어도 시각이 밀리지 않는다.
    """
    assert next_interval_run_at(30, _ms("2026-08-28T12:05:00")) == _ms("2026-08-28T12:30:00")
    assert next_interval_run_at(30, _ms("2026-08-28T12:29:59")) == _ms("2026-08-28T12:30:00")
    assert next_interval_run_at(30, _ms("2026-08-28T12:44:00")) == _ms("2026-08-28T13:00:00")


def test_boundary_moves_forward_not_in_place() -> None:
    """경계에 정확히 걸린 순간에도 다음 경계를 줘야 한다. 아니면 같은 tick 에 무한 반복된다."""
    now = _ms("2026-08-28T12:30:00")
    assert next_interval_run_at(30, now) == _ms("2026-08-28T13:00:00")


def test_result_is_always_in_the_future() -> None:
    now = _ms("2026-08-28T12:17:23")
    for minutes in (5, 15, 30, 60, 180, 360, 1440):
        assert next_interval_run_at(minutes, now) > now, f"interval={minutes}"


def test_zero_interval_is_a_programming_error() -> None:
    """주기가 없는 소스는 `next_run_at` 을 써야 한다. 조용히 기본값을 만들지 않는다."""
    with pytest.raises(ValueError):
        next_interval_run_at(0, _ms("2026-08-28T12:00:00"))

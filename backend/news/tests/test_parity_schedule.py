"""다음 실행 시각 동일성."""

from __future__ import annotations

from news.crawler.schedule import next_run_at


def test_next_run_cases_match(parity: dict) -> None:
    for case in parity["nextRunAt"]:
        actual = next_run_at(case["hour"], case["now"])
        assert actual == case["nextRunAt"], f"hour={case['hour']}"


def test_always_in_the_future(now_ms: int) -> None:
    for hour in range(24):
        assert next_run_at(hour, now_ms) > now_ms, f"hour={hour}"


def test_hour_is_clamped(now_ms: int) -> None:
    assert next_run_at(-5, now_ms) == next_run_at(0, now_ms)
    assert next_run_at(99, now_ms) == next_run_at(23, now_ms)

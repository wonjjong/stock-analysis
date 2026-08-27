"""
LLM 어댑터 동일성. 실패 분류와 쿨다운 계산이 핵심이다.

쿨다운이 틀리면 공급자를 너무 오래 쉬게 해서 무료 한도를 낭비하거나, 너무 짧게 쉬게 해서
같은 오류로 계속 두들기다 밴당한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from news.crawler.llm import (
    FailureKind,
    LlmError,
    classify_failure,
    cooldown_until,
    extract_json,
    timeout_ms,
)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def test_classify_cases_match(parity: dict) -> None:
    llm = parity.get("llm")
    if not llm:
        pytest.skip("정답지에 LLM 기준값이 없습니다.")
    for case in llm["classify"]:
        actual = classify_failure(case["status"], case["detail"])
        assert actual == case["kind"], f"status={case['status']} detail={case['detail']!r}"


def test_cooldown_cases_match(parity: dict) -> None:
    llm = parity.get("llm")
    if not llm:
        pytest.skip("정답지에 LLM 기준값이 없습니다.")
    for case in llm["cooldown"]:
        actual = cooldown_until(case["kind"], _dt(case["now"]))
        assert _ms(actual) == case["until"], (
            f"{case['kind']} at {_dt(case['now']).isoformat()}"
        )


def test_quota_cooldown_stops_at_kst_midnight() -> None:
    """
    한도 초과는 한 시간 쉬되 한국시간 자정을 넘지 않는다 — 자정이면 무료 티어 사용량이
    초기화되므로 더 쉬는 것은 낭비다.
    """
    # KST 23:40 → 자정까지 20분. 1시간보다 가까우므로 자정에 멈춘다.
    late = datetime(2026, 8, 27, 14, 40, tzinfo=UTC)
    until = cooldown_until(FailureKind.QUOTA, late)
    assert until - late == timedelta(minutes=20)

    # KST 18:30 → 자정까지 5시간 30분. 1시간이 더 가깝다.
    early = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)
    assert cooldown_until(FailureKind.QUOTA, early) - early == timedelta(hours=1)


def test_cooldown_durations() -> None:
    now = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
    assert cooldown_until(FailureKind.AUTH, now) - now == timedelta(hours=6)
    assert cooldown_until(FailureKind.REQUEST, now) - now == timedelta(minutes=30)
    assert cooldown_until(FailureKind.TRANSIENT, now) - now == timedelta(minutes=5)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
        ('설명입니다.\n{"a": 1}\n끝', {"a": 1}),
        ('앞{"a": {"b": 2}}뒤', {"a": {"b": 2}}),
    ],
)
def test_extract_json(text: str, expected: dict) -> None:
    """코드펜스로 감싸거나 설명을 덧붙이는 모델이 많다."""
    assert extract_json(text) == expected


@pytest.mark.parametrize("text", ["설명만 있고 JSON 이 없습니다", "", "}{"])
def test_extract_json_rejects_non_json(text: str) -> None:
    with pytest.raises(LlmError):
        extract_json(text)


def test_timeout_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNALIST_LLM_TIMEOUT_MS", "1")
    assert timeout_ms() == 5_000
    monkeypatch.setenv("SIGNALIST_LLM_TIMEOUT_MS", "999999")
    assert timeout_ms() == 60_000
    monkeypatch.setenv("SIGNALIST_LLM_TIMEOUT_MS", "잘못된값")
    assert timeout_ms() == 25_000
    monkeypatch.delenv("SIGNALIST_LLM_TIMEOUT_MS")
    assert timeout_ms() == 25_000

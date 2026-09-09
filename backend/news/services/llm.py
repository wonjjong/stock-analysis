"""
공급자 페일오버. `app/lib/llm.ts` 의 DB 부분 이식.

우선순위가 낮은 숫자부터 호출하고, 실패하면 종류별 쿨다운을 걸어 다음 공급자로 넘어간다.
전부 막히면 호출부가 규칙 기반 결과를 그대로 쓴다 — 키가 없어도 파이프라인이 돈다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from django.db.models import F

from news.crawler.llm import (
    FailureKind,
    LlmConfig,
    LlmError,
    cooldown_until,
    env_config,
    llm_json,
    timeout_ms,
)
from news.models import LlmProvider

logger = logging.getLogger(__name__)

KST_OFFSET = timedelta(hours=9)
# DB 행이 아닌 환경변수 폴백을 나타내는 가짜 id.
ENV_PROVIDER_ID = 0
_DAILY_QUOTA_HINT = re.compile(r"per.?day|requests?.?per.?day|tokens?.?per.?day|rpd|daily", re.IGNORECASE)
_RETRY_DELAY_HINT = re.compile(r"retryDelay[^0-9]{0,12}(\d+(?:\.\d+)?)s", re.IGNORECASE)


@dataclass(slots=True)
class Candidate:
    """DB 행과 환경변수 폴백을 같은 모양으로 다룬다."""

    id: int
    name: str
    config: LlmConfig


@dataclass(slots=True)
class Attempt:
    name: str
    kind: str
    detail: str = ""


@dataclass(slots=True)
class ChainResult:
    parsed: object | None
    provider_name: str | None
    attempts: list[Attempt]


def date_kst(now: datetime) -> str:
    return (now + KST_OFFSET).strftime("%Y-%m-%d")


def available_providers(now: datetime) -> list[Candidate]:
    """
    지금 쓸 수 있는 공급자만 우선순위 순으로.

    쿨다운 중이거나 오늘 한도를 채운 것은 제외한다. `daily_limit = 0` 은 한도 없음이고,
    한국시간 날짜가 바뀌면 사용량은 0부터 다시 센다.
    """
    rows = list(LlmProvider.objects.filter(is_active=True).exclude(api_key="").order_by("priority", "id"))

    if not rows:
        # DB 에 하나도 없을 때만 환경변수를 마지막 수단으로 끼워 넣는다.
        fallback = env_config()
        if fallback is None:
            return []
        return [Candidate(ENV_PROVIDER_ID, "환경변수", fallback)]

    today = date_kst(now)
    usable: list[Candidate] = []
    for row in rows:
        if row.cooldown_until and row.cooldown_until > now:
            continue
        if row.daily_limit:
            same_day = row.usage_date_kst and row.usage_date_kst.strftime("%Y-%m-%d") == today
            if same_day and row.used_today >= row.daily_limit:
                continue
        usable.append(
            Candidate(
                row.pk,
                row.name,
                LlmConfig(row.base_url.rstrip("/"), row.api_key, row.model, timeout_ms()),
            )
        )
    return usable


def _record_success(provider_id: int, now: datetime) -> None:
    if not provider_id:
        return
    today = date_kst(now)
    # 날짜가 같으면 누적, 바뀌었으면 1로 리셋. TS 의 CASE WHEN 과 같다.
    same_day = LlmProvider.objects.filter(pk=provider_id, usage_date_kst=today)
    if same_day.exists():
        same_day.update(used_today=F("used_today") + 1)
    else:
        LlmProvider.objects.filter(pk=provider_id).update(used_today=1)
    LlmProvider.objects.filter(pk=provider_id).update(
        usage_date_kst=today,
        cooldown_until=None,
        last_status="정상",
        last_error=None,
        last_used_at=now,
        success_count=F("success_count") + 1,
        updated_at=now,
    )


def _record_failure(provider_id: int, kind: str, message: str, now: datetime) -> None:
    if not provider_id:
        return
    today = date_kst(now)
    same_day = LlmProvider.objects.filter(pk=provider_id, usage_date_kst=today)
    if same_day.exists():
        same_day.update(used_today=F("used_today") + 1)
    else:
        LlmProvider.objects.filter(pk=provider_id).update(used_today=1)
    until = cooldown_until(kind, now)
    if kind == FailureKind.QUOTA and message.startswith("429"):
        if _DAILY_QUOTA_HINT.search(message):
            kst = now + KST_OFFSET
            until = datetime(kst.year, kst.month, kst.day, tzinfo=UTC) + timedelta(days=1) - KST_OFFSET
        else:
            match = _RETRY_DELAY_HINT.search(message)
            seconds = max(15.0, min(300.0, float(match.group(1)))) if match else 60.0
            until = now + timedelta(seconds=seconds)
    LlmProvider.objects.filter(pk=provider_id).update(
        usage_date_kst=today,
        cooldown_until=until,
        last_status=kind,
        last_error=message[:1000],
        last_used_at=now,
        failure_count=F("failure_count") + 1,
        updated_at=now,
    )


def llm_json_with_failover(system: str, user: str, now: datetime | None = None) -> ChainResult:
    now = now or datetime.now(tz=UTC)
    attempts: list[Attempt] = []

    with httpx.Client() as client:
        for candidate in available_providers(now):
            try:
                parsed = llm_json(client, candidate.config, system, user)
            except LlmError as reason:
                _record_failure(candidate.id, reason.kind, str(reason), now)
                attempts.append(Attempt(candidate.name, reason.kind, str(reason)[:160]))
                continue
            except Exception as reason:
                _record_failure(candidate.id, FailureKind.TRANSIENT, str(reason), now)
                attempts.append(Attempt(candidate.name, FailureKind.TRANSIENT, str(reason)[:160]))
                continue
            _record_success(candidate.id, now)
            attempts.append(Attempt(candidate.name, FailureKind.SUCCESS))
            return ChainResult(parsed, candidate.name, attempts)

    return ChainResult(None, None, attempts)


def provider_stats() -> dict[str, object]:
    """`/news/providers` 화면과 상태 조회용."""
    now = datetime.now(tz=UTC)
    rows = LlmProvider.objects.all()
    return {
        "total": rows.count(),
        "active": rows.filter(is_active=True).exclude(api_key="").count(),
        "cooling": rows.filter(cooldown_until__gt=now).count(),
        "usable": len(available_providers(now)),
        "envFallback": env_config() is not None,
    }


def is_configured() -> bool:
    """공급자가 하나라도 쓸 수 있는지. 없으면 규칙 기반으로만 돈다."""
    return bool(
        LlmProvider.objects.filter(is_active=True).exclude(api_key="").exists() or env_config() is not None
    )

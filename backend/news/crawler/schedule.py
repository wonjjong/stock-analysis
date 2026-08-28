"""다음 실행 시각. `app/lib/news-crawler.ts` 의 nextRunAt 이식."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

DAY_MS = 24 * 60 * 60 * 1000
KST_OFFSET_MS = 9 * 60 * 60 * 1000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def next_run_at(hour_kst: float, now: int) -> int:
    """
    오늘 한국시간 `hour_kst` 시가 이미 지났으면 내일 같은 시각.

    `zoneinfo("Asia/Seoul")` 로 "현대화"하지 말 것. KST 에 DST 가 없어서 +9h 산술이
    맞지만, zoneinfo 는 1961년 이전에 +8:30 을, 1987~88 년에 DST 를 준다. 뉴스에는
    무관하나 장기 KRX 백테스팅에서는 실제 버그가 된다.
    """
    safe_hour = max(0, min(23, math.trunc(hour_kst)))
    kst = _EPOCH + timedelta(milliseconds=now + KST_OFFSET_MS)
    # JS: Date.UTC(y, m, d, safeHour - 9, 0, 0, 0) — hour 가 음수면 전날로 넘어간다.
    base = datetime(kst.year, kst.month, 1, tzinfo=UTC)
    target_dt = base + timedelta(days=kst.day - 1, hours=safe_hour - 9)
    target = int((target_dt - _EPOCH).total_seconds() * 1000)
    if target <= now:
        target += DAY_MS
    return target


# ── 주기(interval) 기반 스케줄 ────────────────────────────────────────────────
#
# `next_run_at` 은 하루 한 번이다. 30분처럼 짧은 주기는 표현할 수 없어 별도 함수를 둔다.
# 이식 동일성(parity) 대상이 아니므로 원본에 대응물이 없다 — `next_run_at` 쪽을 고쳐
# 겸용으로 만들지 않는 이유가 그것이다.

MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60


def clamp_interval_minutes(minutes: float | None) -> int:
    """`clamp_window_hours` 와 같은 의미. 0 이하·NaN·None 은 0(주기 없음)으로 떨어진다."""
    if minutes is None or (isinstance(minutes, float) and (math.isnan(minutes) or math.isinf(minutes))):
        return 0
    value = math.trunc(minutes)
    if value <= 0:
        return 0
    return max(MIN_INTERVAL_MINUTES, min(MAX_INTERVAL_MINUTES, value))


def next_interval_run_at(interval_minutes: float, now: int) -> int:
    """
    다음 주기 **경계**를 돌려준다. `now + interval` 이 아니다.

    경계에 붙이면 30분 주기가 매시 정각·30분에 돌아 사람이 로그를 읽을 수 있고, 실행이
    조금 늦어져도 다음 실행이 밀리지 않는다(`now + interval` 은 지연이 누적된다).
    경계 계산은 UTC 로 하지만 30·60 분처럼 60 의 약수·배수인 주기는 KST(+9:00 정각
    오프셋)에서도 같은 벽시계 시각에 떨어진다.
    """
    step = clamp_interval_minutes(interval_minutes) * 60 * 1000
    if step <= 0:
        raise ValueError("주기가 설정되지 않은 소스에는 쓸 수 없습니다.")
    return (now // step + 1) * step

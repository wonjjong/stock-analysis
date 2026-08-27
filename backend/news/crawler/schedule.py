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

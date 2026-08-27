"""
수집 창. `app/lib/news-crawler.ts` 의 clampWindowHours / selectRecentItems 이식.

"한국시간 오늘"이 아니라 "발행 후 경과 시간"으로 고른다. 미국 매체가 현지 오후에 낸
기사는 한국시간으로 어제와 오늘에 걸쳐 흩어지므로 같은 날짜 비교로는 대부분 누락된다.
하루 한 번 실행에 36시간 창을 쓰면 12시간이 겹쳐 빈 구간이 생기지 않고, 겹치는 부분은
canonical_url 유니크 인덱스가 흡수한다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .types import FeedItem

DEFAULT_WINDOW_HOURS = 36
MIN_WINDOW_HOURS = 6
MAX_WINDOW_HOURS = 168
# 언론사가 몇 분 앞서 찍는 일이 있다. 그 기사를 버리지 않는다.
CLOCK_SKEW_MS = 2 * 60 * 60 * 1000


def clamp_window_hours(hours: float) -> int:
    """
    JS `Math.trunc` + `Number.isFinite` 의미를 그대로. NaN·Infinity·0 이하는 기본값으로
    떨어진다.
    """
    if hours is None or (isinstance(hours, float) and (math.isnan(hours) or math.isinf(hours))):
        return DEFAULT_WINDOW_HOURS
    value = math.trunc(hours)
    if value <= 0:
        return DEFAULT_WINDOW_HOURS
    return max(MIN_WINDOW_HOURS, min(MAX_WINDOW_HOURS, value))


def select_recent_items(
    items: Sequence[FeedItem], now: int, window_hours: float = DEFAULT_WINDOW_HOURS
) -> list[FeedItem]:
    oldest = now - clamp_window_hours(window_hours) * 60 * 60 * 1000
    return [
        item
        for item in items
        if item.published_at is not None
        and item.published_at >= oldest
        and item.published_at <= now + CLOCK_SKEW_MS
    ]

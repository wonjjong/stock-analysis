"""
발행시각 판독. `app/lib/news-crawler.ts` 의 parseDate / parseVisibleDate / dateKst 이식.

이 파일이 이식 전체에서 가장 위험하다. 실패가 예외로 드러나지 않기 때문이다 — 파서가
조금이라도 덜 관대해지면 기사가 조용히 버려지고 `새 기사 없음` 으로 기록된다. 정상처럼
보이므로 몇 주간 모른다.

## 지켜야 할 규칙

1. **`dateutil` 을 쓰지 않는다.** `Date.parse` 보다 관대해서, 원본 주석이 "기사 번호와
   스코어가 그럴듯한 타임스탬프로 둔갑하던" 문제를 일부러 없앴다고 적어둔 그 버그를
   되살린다. `경기 결과 3-2 완승`, `기사 번호 AKR20260827173200001`, `12-3` 은 모두
   None 이어야 한다.
2. **모든 숫자 패턴에 `re.ASCII`.** Python 의 `\\d` 는 유니코드라 전각 숫자(`１２`)나
   데바나가리 숫자까지 매치한다. JS 의 `\\d` 는 ASCII 전용이다.
3. **시각은 정수 밀리초로 다룬다.** 파서 전체가 그 도메인이고 테스트가 그 정수를 그대로
   비교한다. `datetime` 변환은 DB 경계에서 한 번만 한다.
4. **가변 기본값 금지.** `now` 를 기본 인자로 두면 import 시각에 얼어붙는다. 원본이 모든
   함수에 `now` 를 넘기는 구조라 그 성질을 유지한다.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from .text import clean_text

DAY_MS = 24 * 60 * 60 * 1000
KST_OFFSET_MS = 9 * 60 * 60 * 1000
VISIBLE_TEXT_LIMIT = 12_000

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

EXPLICIT_ZONE = re.compile(
    r"(?:Z|[+-]\d{2}:?\d{2}|\b(?:GMT|UTC|UT|KST|JST|CET|CEST|BST|[ECMP][SD]T)\b)",
    re.IGNORECASE | re.ASCII,
)

# parseVisibleDate 의 분기들. 순서가 의미를 가진다.
_ZONED_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*(?:Z|[+-]\d{2}:?\d{2})",
    re.IGNORECASE | re.ASCII,
)
_ZONED_RFC = re.compile(
    r"[A-Z][a-z]{2},\s*\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s+\d{2}:\d{2}(?::\d{2})?\s*(?:GMT|UTC|[+-]\d{4})",
    re.ASCII,
)
_RELATIVE = re.compile(
    r"(\d{1,3})\s*(분|시간|minute|minutes|hour|hours)\s*(?:전|ago)", re.IGNORECASE
)
_RELATIVE_MINUTE = re.compile(r"분|minute", re.IGNORECASE)
_TODAY_CLOCK = re.compile(r"(?:오늘|today)\s*(\d{1,2}):(\d{2})", re.IGNORECASE | re.ASCII)
_TODAY_BARE = re.compile(r"(?:^|[^가-힣a-z])(오늘|today)(?:[^가-힣a-z]|$)", re.IGNORECASE)
_FULL = re.compile(
    r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})(?:[\sT]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
    re.ASCII,
)
_SHORT = re.compile(r"(?:^|[^\d])(\d{1,2})[.-](\d{1,2})\s+(\d{1,2}):(\d{2})", re.ASCII)
_KOREAN = re.compile(r"(\d{1,2})월\s*(\d{1,2})일(?:\s*(\d{1,2})시(?:\s*(\d{1,2})분)?)?", re.ASCII)


def _to_ms(moment: datetime) -> int:
    return int((moment - _EPOCH).total_seconds() * 1000)


def kst_timestamp(
    year: int, month: int, day: int, hour: int, minute: int, second: int = 0
) -> int | None:
    """
    한국시간 (year, month, day, hour, minute, second) 를 UTC 밀리초로.

    원본은 `Date.UTC(year, month - 1, day, hour - 9, minute, second)` 를 쓴다. 가드가
    월만 1~12 로 막고 일은 1~31 만 보므로 2월 30일 같은 값이 통과한 뒤 **오버플로**한다
    (JS 는 2026-02-30 을 2026-03-02 로 정규화한다). `hour - 9` 가 음수가 되어 전날로
    넘어가는 것도 같은 성질이다.

    `datetime(year, month, 1) + timedelta(...)` 가 그 오버플로를 정확히 재현한다.
    """
    if month < 1 or month > 12 or day < 1 or day > 31 or hour > 23 or minute > 59 or second > 59:
        return None
    try:
        base = datetime(year, month, 1, tzinfo=UTC)
    except ValueError:
        # 연도가 datetime 범위를 벗어나는 경우. JS 는 NaN 을 주고 원본은 null 로 흘린다.
        return None
    try:
        moment = base + timedelta(days=day - 1, hours=hour - 9, minutes=minute, seconds=second)
    except (OverflowError, ValueError):
        return None
    return _to_ms(moment)


def yearless_timestamp(month: int, day: int, hour: int, minute: int, now: int) -> int | None:
    """
    목록이 "08-27 18:18" 처럼 연도를 빼고 찍는 경우. 현재 한국시간의 연도를 가정하고,
    그 결과가 미래로 하루 넘게 벌어지면 한 해를 되돌린다(연말 목록을 연초에 읽는 경우).
    """
    year = (_EPOCH + timedelta(milliseconds=now + KST_OFFSET_MS)).year
    time = kst_timestamp(year, month, day, hour, minute)
    if time is None:
        return None
    if time - now > DAY_MS:
        return kst_timestamp(year - 1, month, day, hour, minute)
    return time


def date_kst(time_ms: int) -> str:
    """UTC 밀리초를 한국시간 날짜 문자열(YYYY-MM-DD)로."""
    return (_EPOCH + timedelta(milliseconds=time_ms + KST_OFFSET_MS)).strftime("%Y-%m-%d")


def _js_date_parse_zoned(value: str) -> int | None:
    """
    타임존이 명시된 문자열만 다루는 `Date.parse` 대응물.

    parseVisibleDate 가 이 함수를 호출하는 지점은 두 정규식 중 하나가 매치한 뒤이므로
    입력 형태가 ISO-8601(+오프셋/Z) 또는 RFC-822 로 한정된다. 범용 파서가 필요하지 않고,
    범용 파서를 쓰면 안 된다(관대해지는 것이 곧 버그다).
    """
    text = value.strip()

    # ISO-8601. `Z` 와 오프셋의 콜론 없는 형태(+0900)를 fromisoformat 이 받는 꼴로 맞춘다.
    iso = text.replace(" ", "T", 1) if " " in text[:11] else text
    iso = re.sub(r"[Zz]$", "+00:00", iso)
    iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
    iso = re.sub(r"\s+", "", iso)
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return None
        return _to_ms(parsed.astimezone(UTC))

    # RFC-822 / RFC-2822. RSS 의 pubDate 가 이 형태다.
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return _to_ms(parsed.astimezone(UTC))


def parse_visible_date(value: str, now: int) -> int | None:
    """
    화면에 보이는 목록 텍스트에서 발행시각을 읽는다.

    모든 분기가 구체적인 날짜 토큰을 요구한다. 주변 텍스트를 통째로 파서에 넣으면 기사
    번호와 스코어가 그럴듯한 타임스탬프로 둔갑한다 — 원본이 그것을 일부러 없앴다.
    """
    compact = clean_text(value, VISIBLE_TEXT_LIMIT)
    if not compact:
        return None

    zoned = _ZONED_ISO.search(compact) or _ZONED_RFC.search(compact)
    if zoned:
        time = _js_date_parse_zoned(zoned.group(0))
        if time is not None:
            return time

    relative = _RELATIVE.search(compact)
    if relative:
        unit = 60_000 if _RELATIVE_MINUTE.search(relative.group(2)) else 3_600_000
        return now - int(relative.group(1)) * unit

    today_clock = _TODAY_CLOCK.search(compact)
    if today_clock:
        kst = _EPOCH + timedelta(milliseconds=now + KST_OFFSET_MS)
        return kst_timestamp(
            kst.year, kst.month, kst.day, int(today_clock.group(1)), int(today_clock.group(2))
        )
    if _TODAY_BARE.search(compact):
        return now

    full = _FULL.search(compact)
    if full:
        return kst_timestamp(
            int(full.group(1)),
            int(full.group(2)),
            int(full.group(3)),
            int(full.group(4) or 0),
            int(full.group(5) or 0),
            int(full.group(6) or 0),
        )

    # 연도 없는 숫자 형태는 시각이 함께 있어야만 인정한다. 그러지 않으면 본문의 "12-3"
    # 같은 것이 발행일로 등록된다.
    short = _SHORT.search(compact)
    if short:
        return yearless_timestamp(
            int(short.group(1)), int(short.group(2)),
            int(short.group(3)), int(short.group(4)), now,
        )

    korean = _KOREAN.search(compact)
    if korean:
        return yearless_timestamp(
            int(korean.group(1)), int(korean.group(2)),
            int(korean.group(3) or 0), int(korean.group(4) or 0), now,
        )

    return None


def parse_date(value: str, now: int) -> int | None:
    """
    피드의 시각 필드용. 타임존이 명시되어 있으면 절대시각으로 신뢰하고, 없으면
    한국시간으로 읽는다.

    타임존 없는 시각을 실행 환경의 로컬로 읽으면(JS `Date.parse` 의 기본 동작) 개발은
    KST, 서버는 UTC라 국내 피드가 9시간 미래로 기록되어 전부 탈락한다.
    """
    compact = clean_text(value, 120)
    if not compact:
        return None
    if EXPLICIT_ZONE.search(compact):
        time = _js_date_parse_zoned(compact)
        if time is not None:
            return time
    return parse_visible_date(compact, now)

"""1단계 확인: Django·pytest 기반과 이식 정답지가 준비되었는지."""

import pytest
from django.conf import settings


def test_settings_are_loaded() -> None:
    assert settings.TIME_ZONE == "Asia/Seoul"
    assert settings.USE_TZ is True
    assert settings.DATABASES["default"]["ENGINE"].endswith("postgresql")


def test_parity_baseline_is_available(parity: dict, now_ms: int) -> None:
    """정답지가 존재하고 기대한 사례 수를 담고 있는지."""
    assert now_ms > 0
    expected_groups = {
        "dates": 38, "dateKst": 5, "sourceUrls": 18, "urlsViaAnchors": 22,
        "pagination": 5, "window": 13, "clampWindowHours": 10, "nextRunAt": 8,
        "robots": 8, "analysis": 5, "keywords": 2, "symbols": 5, "body": 3,
    }
    for group, count in expected_groups.items():
        assert group in parity, f"정답지에 {group} 가 없습니다"
        assert len(parity[group]) == count, f"{group}: {len(parity[group])}개 (기대 {count})"
    assert parity["feedFixture"], "RSS 픽스처 결과가 비어 있습니다"
    assert parity["htmlFixture"]["items"], "HTML 픽스처 결과가 비어 있습니다"


def test_date_baseline_includes_the_rejections(parity: dict) -> None:
    """
    날짜로 오인해선 안 되는 입력들이 정답지에서 실제로 None 인지.

    이 단정이 이식의 핵심이다. 파서가 조금이라도 관대해지면 기사 번호나 스코어가
    발행일로 둔갑하고, 반대로 덜 관대해지면 기사가 조용히 버려진다.
    """
    rejected = {c["input"]: c["parseVisibleDate"] for c in parity["dates"]}
    for text in ("경기 결과 3-2 완승", "기사 번호 AKR20260827173200001", "조회수 1,234",
                 "1-0", "부산 2-1 승리", "12", "12-3", "2026", "댓글 5"):
        assert rejected[text] is None, f"{text!r} 가 날짜로 읽혔습니다"


@pytest.mark.django_db
def test_existing_tables_are_reachable() -> None:
    """TypeScript 가 소유한 테이블을 Django 커넥션으로 읽을 수 있는지."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM news_sources")
        assert cursor.fetchone()[0] >= 0

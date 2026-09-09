from datetime import UTC, datetime, timedelta

import pytest

from news.crawler.llm import FailureKind
from news.models import LlmProvider
from news.services.llm import _record_failure


@pytest.fixture
def provider(db):
    now = datetime(2026, 9, 9, tzinfo=UTC)
    return LlmProvider.objects.create(
        name="Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-3.7-flash",
        api_key="test-key",
        created_at=now,
        updated_at=now,
    )


def test_minute_quota_uses_retry_delay(provider):
    now = datetime(2026, 9, 9, 1, tzinfo=UTC)
    _record_failure(
        provider.pk,
        FailureKind.QUOTA,
        '429 RESOURCE_EXHAUSTED {"retryDelay": "27s"}',
        now,
    )
    provider.refresh_from_db()
    assert provider.cooldown_until == now + timedelta(seconds=27)


def test_unspecified_429_uses_one_minute_cooldown(provider):
    now = datetime(2026, 9, 9, 1, tzinfo=UTC)
    _record_failure(provider.pk, FailureKind.QUOTA, "429 RESOURCE_EXHAUSTED", now)
    provider.refresh_from_db()
    assert provider.cooldown_until == now + timedelta(minutes=1)


def test_daily_quota_waits_until_kst_midnight(provider):
    now = datetime(2026, 9, 9, 13, tzinfo=UTC)  # KST 22:00
    _record_failure(
        provider.pk,
        FailureKind.QUOTA,
        "429 GenerateRequestsPerDayPerProject RPD exceeded",
        now,
    )
    provider.refresh_from_db()
    assert provider.cooldown_until == datetime(2026, 9, 9, 15, tzinfo=UTC)

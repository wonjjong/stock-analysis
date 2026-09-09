from datetime import UTC, datetime

import httpx
import pytest

from research.services.news_search import (
    MAX_RESPONSE_BYTES,
    GdeltNewsSearch,
    NaverNewsSearch,
    NewsSearchError,
    NewsSearchUnavailable,
)
from research.stock_news import StockNewsQuery


@pytest.fixture
def query():
    return StockNewsQuery(
        "TESTX", "US", "Test Company", ("Test Incorporated",),
        datetime(2026, 8, 8, tzinfo=UTC), datetime(2026, 9, 8, tzinfo=UTC),
    )


def test_naver_search_alias_budget_and_normalization(settings, query):
    settings.SIGNALIST_NAVER_CLIENT_ID = "test-id"
    settings.SIGNALIST_NAVER_CLIENT_SECRET = "test-secret"
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["X-Naver-Client-Id"] == "test-id"
        return httpx.Response(200, json={"items": [{
            "title": "<b>Test Company</b> &amp; profits", "description": "<b>Growth</b>",
            "originallink": "https://example.com/article", "link": "https://naver.com/a",
            "pubDate": "Mon, 07 Sep 2026 09:00:00 +0900",
        }, {"title": "Invalid", "pubDate": "wrong"}, {
            "title": "Old", "pubDate": "Mon, 07 Sep 2020 09:00:00 +0900",
        }]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        items = NaverNewsSearch(client).search(query)
    assert len(items) == len(query.terms)
    assert {r.url.params["query"] for r in requests} == set(query.terms)
    assert sum(int(r.url.params["display"]) for r in requests) == 50
    assert items[0].evidence.title == "Test Company & profits"
    assert items[0].evidence.summary == "Growth"
    assert items[0].evidence.url == "https://example.com/article"
    assert items[0].evidence.observed_at == "2026-09-07T00:00:00+00:00"
    assert items[0].evidence.available_at == query.until.isoformat()


def test_naver_missing_credentials_no_request(settings, query):
    settings.SIGNALIST_NAVER_CLIENT_ID = ""
    settings.SIGNALIST_NAVER_CLIENT_SECRET = ""
    with pytest.raises(NewsSearchUnavailable):
        NaverNewsSearch().search(query)


def test_gdelt_query_and_seen_date(query):
    def respond(request):
        assert request.url.params["maxrecords"] == "12"
        assert request.url.params["startdatetime"] == "20260808000000"
        assert request.url.params["query"] == '("Test Company" OR "Test Incorporated" OR "TESTX")'
        return httpx.Response(200, json={"articles": [{
            "title": "Test Company profit", "url": "https://example.com/a", "seendate": "20260907T010203Z",
        }, {"title": "Bad", "seendate": None}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        items = GdeltNewsSearch(client).search(query)
    assert len(items) == 1
    assert items[0].provider == "GDELT"
    assert items[0].evidence.observed_at == "2026-09-07T01:02:03+00:00"
    assert "실제 발행일은 확인되지 않음" in items[0].evidence.summary


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="not JSON"),
    httpx.Response(200, json=[]),
    httpx.Response(200, json={"articles": {}}),
    httpx.Response(503, text="unavailable"),
    httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)),
])
def test_gdelt_bad_responses_are_provider_errors(query, response):
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client,
        pytest.raises(NewsSearchError),
    ):
        GdeltNewsSearch(client).search(query)


def test_timeout_is_provider_error(query):
    def respond(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(NewsSearchError, match="시간 초과"),
    ):
        GdeltNewsSearch(client).search(query)


def test_gdelt_rate_limit_includes_provider_cause(query, monkeypatch):
    monkeypatch.setattr("research.services.news_search.time.sleep", lambda _: None)
    response = httpx.Response(429, text="Please limit requests to one every 5 seconds.")
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client,
        pytest.raises(NewsSearchError, match="요청 빈도 제한"),
    ):
        GdeltNewsSearch(client).search(query)


def test_gdelt_limit_and_empty_results(query):
    row = {"title": "Test Company", "url": "https://example.com/a", "seendate": "20260907T010203Z"}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"articles": [row] * 60}),
    )) as client:
        assert len(GdeltNewsSearch(client).search(query)) == 50
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"articles": []}),
    )) as client:
        assert GdeltNewsSearch(client).search(query) == ()

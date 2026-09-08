"""Bounded news-search HTTP adapters; article bodies are never fetched."""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from research.analysis import Evidence
from research.stock_news import NewsItem, StockNewsQuery

MAX_RESULTS = 50
MAX_RESPONSE_BYTES = 512 * 1024
REQUEST_TIMEOUT = 5.0


class NewsSearchError(RuntimeError):
    """A provider failed; callers may continue with other evidence."""


class NewsSearchUnavailable(NewsSearchError):
    """Provider credentials are not configured."""


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", value)).split())


def _url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {"http", "https"} and parsed.hostname else ""
    except ValueError:
        return ""


def _terms(query: StockNewsQuery) -> tuple[str, ...]:
    # Keep the ticker even when a company's alias catalogue exceeds our request budget.
    return tuple(dict.fromkeys((*query.terms[:7], query.symbol)))


def _item(provider: str, title: str, summary: str, url: str, date: datetime,
          collected_at: datetime) -> NewsItem:
    identifier = hashlib.sha256(f"{url or title}".encode()).hexdigest()[:24]
    timestamp = date.astimezone(UTC).isoformat()
    return NewsItem(
        evidence=Evidence(
            id=f"{provider.lower()}:{identifier}", kind="news", title=title[:300],
            source=urlsplit(url).hostname or provider, observed_at=timestamp,
            available_at=collected_at.astimezone(UTC).isoformat(), summary=summary[:800], url=url,
        ),
        provider=provider,
    )


class _HttpNewsSearch:
    provider: str

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def _get(
        self, url: str, params: dict, headers: dict | None = None, *, deadline: float | None = None,
    ) -> dict:
        def read(client: httpx.Client) -> dict:
            remaining = REQUEST_TIMEOUT
            if deadline is not None:
                remaining = min(remaining, deadline - time.monotonic())
            if remaining <= 0:
                raise NewsSearchError(f"{self.provider}: 검색 시간 초과")
            with client.stream(
                "GET", url, params=params, headers=headers, timeout=remaining,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    if deadline is not None and time.monotonic() > deadline:
                        raise NewsSearchError(f"{self.provider}: 검색 시간 초과")
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise NewsSearchError(f"{self.provider}: 응답 크기 초과")
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise NewsSearchError(f"{self.provider}: 잘못된 응답 형식")
                return data

        try:
            if self.client is not None:
                return read(self.client)
            with httpx.Client() as client:
                return read(client)
        except httpx.TimeoutException as exc:
            raise NewsSearchError(f"{self.provider}: 검색 시간 초과") from exc
        except httpx.HTTPStatusError as exc:
            raise NewsSearchError(
                f"{self.provider}: 뉴스 검색 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            # Never include request headers, credentials or raw response bodies.
            raise NewsSearchError(f"{self.provider}: 뉴스 검색 HTTP 오류") from exc
        except (ValueError, UnicodeError) as exc:
            raise NewsSearchError(f"{self.provider}: 잘못된 JSON 응답") from exc


class NaverNewsSearch(_HttpNewsSearch):
    provider = "Naver"

    def search(self, query: StockNewsQuery) -> tuple[NewsItem, ...]:
        client_id = getattr(settings, "SIGNALIST_NAVER_CLIENT_ID", "")
        secret = getattr(settings, "SIGNALIST_NAVER_CLIENT_SECRET", "")
        if not client_id or not secret:
            raise NewsSearchUnavailable("Naver: 검색 API 키 미설정")
        terms = _terms(query)
        if not terms:
            return ()
        results = []
        deadline = time.monotonic() + 12
        budget, extra = divmod(MAX_RESULTS, len(terms))
        for index, term in enumerate(terms):
            limit = budget + (index < extra)
            payload = self._get(
                "https://openapi.naver.com/v1/search/news.json",
                {"query": term, "display": limit, "start": 1, "sort": "date"},
                {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": secret},
                deadline=deadline,
            )
            rows = payload.get("items")
            if not isinstance(rows, list):
                raise NewsSearchError("Naver: 기사 목록 응답 누락")
            for row in rows[:limit]:
                if not isinstance(row, dict):
                    continue
                title = _text(row.get("title"))
                try:
                    date = parsedate_to_datetime(row.get("pubDate", ""))
                    if date.tzinfo is None:
                        continue
                    date = date.astimezone(UTC)
                except (ValueError, TypeError, AttributeError):
                    continue
                if not title or not query.since <= date <= query.until:
                    continue
                results.append(_item(
                    self.provider, title, _text(row.get("description")),
                    _url(row.get("originallink")) or _url(row.get("link")), date, query.until,
                ))
        return tuple(results)


class GdeltNewsSearch(_HttpNewsSearch):
    provider = "GDELT"

    def search(self, query: StockNewsQuery) -> tuple[NewsItem, ...]:
        # Strip query-language metacharacters from company aliases.
        terms = [re.sub(r'[^\w\s.-]', ' ', term).strip() for term in _terms(query)]
        terms = [term for term in terms if term]
        if not terms:
            return ()
        expression = " OR ".join(f'"{term}"' for term in terms)
        payload = self._get("https://api.gdeltproject.org/api/v2/doc/doc", {
            "query": f"({expression})" if len(terms) > 1 else expression,
            "mode": "artlist", "format": "json", "maxrecords": MAX_RESULTS,
            "sort": "datedesc", "startdatetime": query.since.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
            "enddatetime": query.until.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
        }, deadline=time.monotonic() + 12)
        rows = payload.get("articles")
        if not isinstance(rows, list):
            raise NewsSearchError("GDELT: 기사 목록 응답 누락")
        results = []
        for row in rows[:MAX_RESULTS]:
            if not isinstance(row, dict):
                continue
            title = _text(row.get("title"))
            try:
                date = datetime.strptime(row.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue
            if not title or not query.since <= date <= query.until:
                continue
            results.append(_item(
                self.provider, title,
                "GDELT 최초 수집 시각 기준이며 실제 발행일은 확인되지 않음. 기사 제목만 제공됨.",
                _url(row.get("url")), date, query.until,
            ))
        return tuple(results)

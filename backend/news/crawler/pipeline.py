"""
수집 오케스트레이션. `app/lib/news-crawler.ts` 의 collectHtmlPages /
fetchSourceItems 이식. DB 는 모르고, 결과만 돌려준다(쓰기는 services 층).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from .feed import MAX_ITEMS_PER_RUN, looks_like_feed, parse_feed
from .fetcher import CrawlError, Fetched, assert_robots_allowed, safe_fetch
from .html import find_next_page_url, parse_news_page
from .jsurl import InvalidSourceUrl, validate_source_url
from .text import decode_xml
from .types import FeedItem, SourceSpec
from .window import select_recent_items

MAX_PAGES_PER_RUN = 10

_FEED_LINK = re.compile(
    r"""<link\b[^>]*\btype=["']application/(?:rss|atom)\+xml["'][^>]*\bhref=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
_FEED_LINK_REVERSED = re.compile(
    r"""<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\btype=["']application/(?:rss|atom)\+xml["'][^>]*>""",
    re.IGNORECASE,
)


@dataclass(slots=True)
class SourceFetch:
    unchanged: bool
    url: str
    etag: str | None
    last_modified: str | None
    items: list[FeedItem] = field(default_factory=list)


def _dedupe(items: list[FeedItem], limit: int) -> list[FeedItem]:
    unique: dict[str, FeedItem] = {}
    for item in items:
        unique.setdefault(item.url, item)
    return list(unique.values())[:limit]


def collect_html_pages(
    client: httpx.Client,
    first_html: str,
    first_url: str,
    source: SourceSpec,
    now: int,
    robots_cache: dict[str, str],
) -> list[FeedItem]:
    """
    번호 페이저를 최신순으로 따라가며, 창 안의 기사가 없는 페이지가 나오면 멈춘다.
    뒤 페이지는 best-effort 다 — 실패하면 앞 페이지가 이미 모은 것을 유지하고 전체
    실행을 실패시키지 않는다.
    """
    budget = max(1, min(MAX_PAGES_PER_RUN, int(source.max_pages) or 1))
    seen = {first_url}
    html = first_html
    url = first_url
    page_items = parse_news_page(html, url, now)
    collected = list(page_items)

    for _ in range(1, budget):
        if not select_recent_items(page_items, now, source.window_hours):
            break
        next_url = find_next_page_url(html, url)
        if not next_url or next_url in seen:
            break
        seen.add(next_url)
        try:
            assert_robots_allowed(client, next_url, robots_cache)
            fetched = safe_fetch(client, next_url)
            if not fetched.ok:
                break
            html = fetched.text
            url = fetched.final_url
            page_items = parse_news_page(html, url, now)
            if not page_items:
                break
            collected.extend(page_items)
        except (CrawlError, InvalidSourceUrl):
            break

    return _dedupe(collected, MAX_ITEMS_PER_RUN)


def _discovered_feed_url(html: str, base_url: str) -> str:
    match = _FEED_LINK.search(html) or _FEED_LINK_REVERSED.search(html)
    if not match:
        return ""
    from urllib.parse import urljoin

    return validate_source_url(urljoin(base_url, decode_xml(match.group(1))))


def _result(fetched: Fetched, items: list[FeedItem], *, unchanged: bool = False) -> SourceFetch:
    return SourceFetch(
        unchanged=unchanged,
        url=fetched.final_url,
        etag=fetched.headers.get("etag"),
        last_modified=fetched.headers.get("last-modified"),
        items=items,
    )


def fetch_source_items(client: httpx.Client, source: SourceSpec, now: int) -> SourceFetch:
    """
    소스에서 기사 목록을 가져온다.

    순서: robots 확인 → 조건부 요청 → 피드면 바로 파싱 → 아니면 HTML 목록 파싱 →
    페이지에 RSS 링크가 있으면 그쪽을 시도 → 둘 다 실패하면 오류.
    """
    conditional: dict[str, str] = {}
    if source.etag:
        conditional["If-None-Match"] = source.etag
    if source.last_modified:
        conditional["If-Modified-Since"] = source.last_modified

    robots_cache: dict[str, str] = {}
    preferred = source.target
    assert_robots_allowed(client, preferred, robots_cache)

    fetched = safe_fetch(client, preferred, conditional)
    if fetched.status == 304:
        return _result(fetched, [], unchanged=True)
    if not fetched.ok:
        raise CrawlError(f"뉴스 소스 응답 오류 ({fetched.status})")

    text = fetched.text
    if looks_like_feed(text):
        return _result(fetched, parse_feed(text, fetched.final_url, now))

    page_url = fetched.final_url
    page_fetched = fetched
    first_html = text
    has_articles = bool(parse_news_page(first_html, page_url, now))

    try:
        discovered = _discovered_feed_url(first_html, page_url)
    except (InvalidSourceUrl, ValueError):
        discovered = ""

    if not discovered:
        if not has_articles:
            raise CrawlError(
                "발행일을 식별할 수 있는 기사 목록을 찾지 못했습니다."
                " RSS 또는 날짜가 표시된 뉴스 목록 URL을 등록해 주세요."
            )
        return _result(
            page_fetched,
            collect_html_pages(client, first_html, page_url, source, now, robots_cache),
        )

    try:
        assert_robots_allowed(client, discovered, robots_cache)
        feed_fetched = safe_fetch(client, discovered)
        if not feed_fetched.ok:
            raise CrawlError(f"발견한 피드 응답 오류 ({feed_fetched.status})")
        feed_items = (
            parse_feed(feed_fetched.text, feed_fetched.final_url, now)
            if looks_like_feed(feed_fetched.text)
            else []
        )
        if feed_items:
            return _result(feed_fetched, feed_items)
    except (CrawlError, InvalidSourceUrl):
        if not has_articles:
            raise CrawlError(
                "페이지에서 발견한 RSS를 읽지 못했고 HTML 기사 날짜도 식별하지 못했습니다."
            ) from None

    if not has_articles:
        raise CrawlError("뉴스 기사와 발행일을 식별하지 못했습니다.")
    return _result(
        page_fetched,
        collect_html_pages(client, first_html, page_url, source, now, robots_cache),
    )

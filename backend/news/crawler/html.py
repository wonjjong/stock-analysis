"""
HTML 목록 파싱. `app/lib/news-crawler.ts` 의 jsonLdItems / dateFromHtml / alignToTags /
anchorContext / anchorItem / parseNewsPage / findNextPageUrl 이식.

## BeautifulSoup 을 쓰지 않는 이유

`anchor_context` 는 **원시 HTML 을 문자 오프셋(±320)으로 잘라** 문맥을 만든다. bs4 는
파싱된 트리를 주므로 이 동작을 표현할 수 없다. "진짜 최근접 `<li>` 를 찾으면 더 낫지
않나" 싶지만, 그건 **다른 기사 집합**이고 검증할 기준이 없으며 튜닝된 상수(320자,
제목 12자, 앵커 120자)가 전부 무효가 된다.

`alignToTags` 가 존재하는 이유가 이 방식의 위험을 말해 준다 — 오프셋으로 자르면 반쯤
열린 태그가 남고, 그 속성값이 태그 제거 후에도 살아남아
`<img src=".../2019/06/26/...">` 의 경로가 발행일로 읽힌다.

## JS 와 다른 지점

- `re.ASCII`: Python 의 `\\w` · `\\d` 는 유니코드다. JS 는 ASCII 전용이다.
- `str.replace`: JS 는 문자열 인자일 때 **첫 번째만** 바꾼다. Python 은 전부 바꾸므로
  `count=1` 을 반드시 넘긴다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .dates import parse_visible_date
from .jsurl import absolute_article_url, absolute_page_url, page_number
from .text import clean_text, decode_xml
from .types import FeedItem

MAX_ITEMS_PER_PAGE = 60

_LD_SCRIPT = re.compile(
    r"""<script\b[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)
_ARTICLE_TYPE = re.compile(r"NewsArticle|Article|ReportageNewsArticle", re.IGNORECASE)

_DATE_ATTRIBUTE = re.compile(
    r"""<[^>]*\b(?:datetime|data-date|data-published|data-time)=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
_DATE_META = re.compile(
    r"""<meta\b[^>]*\b(?:itemprop|property|name)=["'][^"']*"""
    r"""(?:datePublished|published_time|pubdate|date)[^"']*["'][^>]*\bcontent=["']([^"']+)["']""",
    re.IGNORECASE,
)
_DATE_ELEMENT = re.compile(
    r"""<(\w+)\b[^>]*(?:class|id)=["'][^"']*(?:time|date|pubdt)[^"']*["'][^>]*>(.{0,200}?)</\1>""",
    re.IGNORECASE | re.DOTALL | re.ASCII,
)

_ITEM_BOUNDARY = re.compile(
    r"</?(?:li|article|aside|section|nav|ul|ol|table|tr)\b[^>]*>", re.IGNORECASE
)
_ANCHOR_FULL = re.compile(
    r"""<a\b([^>]*)href=["']([^"']+)["']([^>]*)>(.*?)</a>""", re.IGNORECASE | re.DOTALL
)
_ANCHOR_SIMPLE = re.compile(
    r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.IGNORECASE | re.DOTALL
)
_TITLE_ATTR = re.compile(r"""title=["']([^"']+)["']""", re.IGNORECASE)
_BLOCK = re.compile(r"<(article|li)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_NAV_WORDS = re.compile(
    r"^(로그인|구독|더보기|전체보기|메뉴|홈|login|subscribe|read more)$", re.IGNORECASE
)
_REL_NEXT = re.compile(
    r"""<(?:link|a)\b[^>]*\brel=["']next["'][^>]*\bhref=["']([^"']+)["']""", re.IGNORECASE
)
_REL_NEXT_REVERSED = re.compile(
    r"""<(?:link|a)\b[^>]*\bhref=["']([^"']+)["'][^>]*\brel=["']next["']""", re.IGNORECASE
)
# 번호 페이저용. 원본은 라벨을 120자로 제한한다.
_ANCHOR_LABELLED = re.compile(
    r"""<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>(.{0,120}?)</a>""", re.IGNORECASE | re.DOTALL
)


def _article_type(value: Any) -> bool:
    types = value if isinstance(value, list) else [value]
    return any(isinstance(item, str) and _ARTICLE_TYPE.search(item) for item in types)


def json_ld_items(html: str, page_url: str, now: int) -> list[FeedItem]:
    """
    발행사가 심어 둔 JSON-LD 에서 기사를 읽는다. 여기 실린 날짜는 항상 절대시각이라
    `now` 에 의존하지 않는다(원본이 이 호출에 now 를 넘기지 않는 것과 결과가 같다).
    """
    items: list[FeedItem] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for entry in value:
                visit(entry)
            return
        if not isinstance(value, dict):
            return
        if _article_type(value.get("@type")):
            title = clean_text(str(value.get("headline") or value.get("name") or ""), 500)
            main = value.get("mainEntityOfPage")
            if isinstance(value.get("url"), str):
                link = value["url"]
            elif isinstance(main, str):
                link = main
            elif isinstance(main, dict):
                link = str(main.get("@id") or "")
            else:
                link = ""
            published_at = parse_visible_date(
                str(value.get("datePublished") or value.get("dateCreated") or ""), now
            )
            url = absolute_article_url(link, page_url)
            if title and url and published_at:
                items.append(
                    FeedItem(title, url, clean_text(str(value.get("description") or "")), published_at)
                )
        for entry in value.values():
            visit(entry)

    for match in _LD_SCRIPT.finditer(html):
        try:
            visit(json.loads(decode_xml(match.group(1)).strip()))
        except (ValueError, TypeError):
            # 발행사 메타데이터가 깨진 경우. 원본과 같이 조용히 넘어간다.
            continue
    return items


def date_from_html(block: str, now: int) -> int | None:
    """
    목록 마크업은 시각을 전용 요소(`<span class="txt-time">`)에 넣고, 그 요소가 본문
    전체를 실은 리드 문단 **뒤에** 오는 경우가 흔하다. 그래서 전용 요소를 먼저 읽고
    블록 전체 스캔은 마지막에 한다.
    """
    attribute_match = _DATE_ATTRIBUTE.search(block)
    attribute = attribute_match.group(1) if attribute_match else None
    if attribute is None:
        meta_match = _DATE_META.search(block)
        attribute = meta_match.group(1) if meta_match else None
    if attribute:
        tagged = parse_visible_date(attribute, now)
        if tagged:
            return tagged

    for match in _DATE_ELEMENT.finditer(block):
        stamped = parse_visible_date(match.group(2), now)
        if stamped:
            return stamped

    return parse_visible_date(block, now)


def _align_to_tags(raw: str, side: str) -> str:
    """오프셋 절단으로 남은 반쪽 태그를 잘라낸다."""
    if side == "head":
        opening = raw.find(">")
        return "" if opening < 0 else raw[opening + 1 :]
    closing = raw.rfind("<")
    return raw if closing < 0 else raw[:closing]


def anchor_context(html: str, start: int, end: int) -> str:
    """
    앵커 주변 문맥을 가장 가까운 목록 항목 경계에서 자른다. 이 절단이 없으면 날짜 없는
    "많이 본 기사" 링크가 옆에 렌더된 기사의 시각을 물려받아 엉뚱한 날짜로 분류된다.
    """
    raw_head = html[max(0, start - 320) : start]
    raw_tail = html[end : min(len(html), end + 320)]

    boundaries = list(_ITEM_BOUNDARY.finditer(raw_head))
    if boundaries:
        last = boundaries[-1]
        head = raw_head[last.start() + len(last.group(0)) :]
    else:
        head = _align_to_tags(raw_head, "head")

    next_boundary = _ITEM_BOUNDARY.search(raw_tail)
    tail = raw_tail[: next_boundary.start()] if next_boundary else _align_to_tags(raw_tail, "tail")

    return f"{head}{html[start:end]}{tail}"


def anchor_item(block: str, page_url: str, now: int) -> FeedItem | None:
    ranked: list[tuple[str, str]] = []
    for match in _ANCHOR_FULL.finditer(block):
        attributes = f"{match.group(1)} {match.group(3)}"
        visible_title = clean_text(match.group(4), 500)
        if visible_title:
            title = visible_title
        else:
            attr = _TITLE_ATTR.search(attributes)
            title = clean_text(attr.group(1) if attr else "", 500)
        if len(title) >= 12 and not _NAV_WORDS.match(title):
            ranked.append((title, match.group(2)))
    # JS 의 sort 는 안정적이고 Python 의 sorted 도 안정적이다. 길이 내림차순.
    ranked.sort(key=lambda pair: len(pair[0]), reverse=True)

    if not ranked:
        return None
    title, href = ranked[0]
    published_at = date_from_html(block, now)
    url = absolute_article_url(href, page_url)
    if not url or not published_at:
        return None
    # JS `String.replace(문자열, "")` 은 첫 번째 occurrence 만 지운다. count=1 이 필수다.
    excerpt = clean_text(block, 1200).replace(title, "", 1).strip()
    return FeedItem(title, url, excerpt, published_at)


def parse_news_page(html: str, page_url: str, now: int) -> list[FeedItem]:
    candidates: list[FeedItem] = json_ld_items(html, page_url, now)

    for match in _BLOCK.finditer(html):
        item = anchor_item(match.group(2), page_url, now)
        if item:
            candidates.append(item)

    for match in _ANCHOR_SIMPLE.finditer(html):
        title = clean_text(match.group(2), 500)
        if len(title) < 12:
            continue
        context = anchor_context(html, match.start(), match.end())
        published_at = date_from_html(context, now)
        url = absolute_article_url(match.group(1), page_url)
        if url and published_at:
            candidates.append(FeedItem(title, url, "", published_at))

    unique: dict[str, FeedItem] = {}
    for item in candidates:
        unique.setdefault(item.url, item)
    return list(unique.values())[:MAX_ITEMS_PER_PAGE]


def find_next_page_url(html: str, current_url: str) -> str:
    """
    `rel="next"` 를 먼저 보고, 없으면 **현재 페이지 + 1** 을 가리키는 번호 링크를 찾는다.

    앵커 텍스트만으로는 근거가 약하므로 URL 이 같은 번호를 가리키는지 확인한다. 그리고
    현재 URL 과 같은 결과는 버린다 — 그러지 않으면 같은 페이지를 무한히 다시 읽는다.
    """
    match = _REL_NEXT.search(html) or _REL_NEXT_REVERSED.search(html)
    if match:
        resolved = absolute_page_url(match.group(1), current_url)
        if resolved and resolved != current_url:
            return resolved

    wanted = page_number(current_url) + 1
    for anchor in _ANCHOR_LABELLED.finditer(html):
        if clean_text(anchor.group(2), 20) != str(wanted):
            continue
        candidate = absolute_page_url(anchor.group(1), current_url)
        if candidate and candidate != current_url and page_number(candidate) == wanted:
            return candidate
    return ""

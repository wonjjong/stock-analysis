"""
RSS·Atom 파싱. `app/lib/news-crawler.ts` 의 parseFeed / looksLikeFeed 이식.

## feedparser 를 쓰지 않는 이유

1. HTML 을 기본 sanitize 해서 excerpt 가 달라진다 → 기존 기사 전체의 content_hash 가
   바뀐다.
2. 자체 날짜 파싱 체인을 갖는다. `Date.parse` 와 관대함이 달라 조용한 차이를 만든다.
3. excerpt 우선순위(`content:encoded > content > description > summary`)가 다르다.
4. 깨진 XML 에 더 엄격하다 — 그런데 현 블록 정규식 파서의 관용성이 레지스트리의 지저분한
   한국 소스에 **하중을 받는 기능**이다.

부수적으로, 정규식 파서는 XXE·billion-laughs 에 구조적으로 면역이다. 실제 XML 파서로
가면 그 표면이 부활하므로 그때는 defusedxml 이 필요하다.
"""

from __future__ import annotations

import re

from .dates import parse_date
from .jsurl import absolute_article_url
from .text import clean_text, tag
from .types import FeedItem

MAX_ITEMS_PER_RUN = 200

_RSS_ITEM = re.compile(r"<item(?:\s[^>]*)?>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_ATOM_ENTRY = re.compile(r"<entry(?:\s[^>]*)?>(.*?)</entry>", re.IGNORECASE | re.DOTALL)
_ATOM_HREF = re.compile(r"""<link\b[^>]*\bhref=["']([^"']+)["'][^>]*>""", re.IGNORECASE)
# 루트 태그와 항목 태그를 **둘 다** 요구한다. `<?xml` 만 보면 XML sitemap 이나
# 임의의 XML 문서를 피드로 오인한다.
_FEED_ROOT = re.compile(r"<(rss|feed|rdf:RDF)\b", re.IGNORECASE)
_FEED_ITEM = re.compile(r"<(item|entry)\b", re.IGNORECASE)


def looks_like_feed(text: str) -> bool:
    return bool(_FEED_ROOT.search(text)) and bool(_FEED_ITEM.search(text))


def parse_feed(xml: str, feed_url: str, now: int) -> list[FeedItem]:
    rss_blocks = [match.group(1) for match in _RSS_ITEM.finditer(xml)]
    atom_blocks = [match.group(1) for match in _ATOM_ENTRY.finditer(xml)]
    blocks = rss_blocks or atom_blocks

    # 피드는 목록의 한 페이지가 아니라 한 문서이므로 페이지 단위 몫이 아니라 실행 전체
    # 예산을 받는다.
    items: list[FeedItem] = []
    for block in blocks[:MAX_ITEMS_PER_RUN]:
        title = clean_text(tag(block, ["title"]), 500)
        rss_link = tag(block, ["link", "guid"])
        atom = _ATOM_HREF.search(block)
        atom_href = atom.group(1) if atom else ""
        url = absolute_article_url(atom_href or clean_text(rss_link, 2000), feed_url)
        excerpt = clean_text(tag(block, ["content:encoded", "content", "description", "summary"]))
        published_at = parse_date(tag(block, ["pubDate", "published", "updated", "dc:date"]), now)
        if title and url:
            items.append(FeedItem(title, url, excerpt, published_at))
    return items

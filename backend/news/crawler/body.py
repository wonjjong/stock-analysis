"""
기사 본문 추출. `app/lib/article-body.ts` 이식.

## 크롤러 쪽과 동작이 다르다 — 재사용하면 안 된다

같은 이름의 함수가 `text.py` · `fetcher.py` 에도 있지만 의미가 다르다. 원본이 별도
구현을 둔 것이므로 그 차이를 유지한다.

| | `news-crawler.ts` | `article-body.ts` |
|---|---|---|
| 알 수 없는 named 엔티티 | `&entity;` 로 되돌림 | **공백**으로 바꿈 |
| 크기 초과 | 예외를 던짐 | **읽은 만큼만 쓰고 중단** |
| robots 401·403·5xx | 예외 | **False 반환**(수집 안 함) |
| robots 네트워크 오류 | 예외 | **True 반환**(수집함) |
| 상한 | 2.5MB | 1.5MB |
| robots 타임아웃 | 12초 | 8초 |

## 원문을 저장하지 않는다

본문은 분석 입력으로만 쓰고 글자 수만 DB 에 남긴다. README 의 저작권 방침이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from .jsurl import validate_source_url
from .robots import robots_allows

USER_AGENT = "SignalistResearchBot/1.1 (+daily public news indexer; owner-managed sources)"
MAX_BYTES = 1_500_000
MAX_BODY_CHARS = 9_000
MIN_PARAGRAPH_CHARS = 20
MAX_ROBOTS_CHARS = 200_000
PAGE_TIMEOUT = 12.0
ROBOTS_TIMEOUT = 8.0
MAX_REDIRECTS = 3
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# 언론사 페이지 하단의 저작권·제보·구독 안내는 본문이 아니라 잡음이다.
_BOILERPLATE = re.compile(
    r"저작권자|무단\s*전재|재배포\s*금지|제보는|구독하기|기사제보|All rights reserved|Copyright ⓒ",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_NOISE_TAGS = re.compile(
    r"<(script|style|noscript|iframe|svg|form|nav|header|footer|aside)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_BLOCK = re.compile(r"<(article|section|div)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&(#x?[0-9a-f]+|[a-z]+);", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}


class BodyError(RuntimeError):
    """본문 수집 실패. 메시지가 `news_insights.error` 에 저장된다."""


@dataclass(frozen=True, slots=True)
class ArticleBody:
    text: str
    chars: int
    final_url: str
    source: str = "본문"


def _decode_entities(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        entity = match.group(1)
        if entity[0] == "#":
            is_hex = len(entity) > 1 and entity[1].lower() == "x"
            try:
                code = int(entity[2:] if is_hex else entity[1:], 16 if is_hex else 10)
                return chr(code)
            except (ValueError, OverflowError):
                return ""
        # 크롤러 쪽과 달리 알 수 없는 엔티티를 공백으로 바꾼다.
        return _NAMED.get(entity.lower(), " ")

    return _ENTITY.sub(replace, value)


def _text(html: str) -> str:
    return _WHITESPACE.sub(" ", _decode_entities(_TAG.sub(" ", html))).strip()


def _strip_noise(html: str) -> str:
    return _NOISE_TAGS.sub(" ", _COMMENT.sub(" ", html))


def extract_body(html: str) -> str:
    """문단 태그를 모아 본문을 만든다. 문단이 없으면 가장 글자가 많은 블록으로 대체한다."""
    clean = _strip_noise(html)
    paragraphs = [
        value
        for value in (_text(match.group(1)) for match in _PARAGRAPH.finditer(clean))
        if len(value) >= MIN_PARAGRAPH_CHARS and not _BOILERPLATE.search(value)
    ]
    if len(paragraphs) >= 2:
        return "\n".join(paragraphs)[:MAX_BODY_CHARS]

    blocks = sorted(
        (_text(match.group(2)) for match in _BLOCK.finditer(clean)),
        key=len,
        reverse=True,
    )
    best = blocks[0] if blocks else _text(clean)
    return best[:MAX_BODY_CHARS]


def _read_limited(response: httpx.Response) -> str:
    """상한을 넘으면 **예외 없이** 읽은 만큼만 쓴다(크롤러 쪽과 다르다)."""
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_BYTES:
            response.close()
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _allowed_by_robots(
    client: httpx.Client, target: str, cache: dict[str, str]
) -> bool:
    origin = _origin(target)
    if origin in cache:
        return robots_allows(cache[origin], target)
    try:
        response = client.get(
            f"{origin}/robots.txt",
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
            timeout=ROBOTS_TIMEOUT,
        )
    except httpx.HTTPError:
        # 네트워크 오류는 판단 불가가 아니라 "규칙 없음"으로 본다(원본과 같다).
        cache[origin] = ""
        return True

    # 401·403·5xx 는 판단 불가로 보고 수집하지 않는다.
    if response.status_code in (401, 403) or response.status_code >= 500:
        cache[origin] = "User-agent: *\nDisallow: /"
        return False

    rules = response.text[:MAX_ROBOTS_CHARS] if response.status_code < 400 else ""
    cache[origin] = rules
    return robots_allows(rules, target)


def fetch_article_body(
    client: httpx.Client, url: str, robots_cache: dict[str, str] | None = None
) -> ArticleBody:
    """
    기사 원문 페이지에서 본문 텍스트만 가져온다. 원문은 저장하지 않고 분석 입력으로만 쓴다.
    """
    cache = robots_cache if robots_cache is not None else {}
    current = validate_source_url(url)

    for _ in range(MAX_REDIRECTS + 1):
        if not _allowed_by_robots(client, current, cache):
            raise BodyError("robots.txt가 본문 수집을 허용하지 않습니다.")
        try:
            with client.stream(
                "GET",
                current,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=PAGE_TIMEOUT,
            ) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise BodyError("리다이렉트 위치가 없습니다.")
                    current = validate_source_url(urljoin(current, location))
                    continue
                if response.status_code >= 400:
                    raise BodyError(f"본문 페이지 응답이 {response.status_code}입니다.")
                body = extract_body(_read_limited(response))
        except httpx.TimeoutException as reason:
            raise BodyError("본문 페이지 응답 시간이 초과됐습니다.") from reason
        except httpx.HTTPError as reason:
            raise BodyError(f"본문 페이지에 연결하지 못했습니다: {reason}") from reason

        return ArticleBody(text=body, chars=len(body), final_url=current)

    raise BodyError("리다이렉트가 너무 많습니다.")

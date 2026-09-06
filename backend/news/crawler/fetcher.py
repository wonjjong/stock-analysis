"""뉴스 목록 HTTP 요청, robots 확인, 리다이렉트와 응답 제한을 제공한다."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from .jsurl import InvalidSourceUrl, validate_source_url
from .robots import robots_allows

MAX_FEED_BYTES = 2_500_000
USER_AGENT = "SignalistResearchBot/1.1 (+daily public news indexer; owner-managed sources)"
DEADLINE_SECONDS = 12.0
MAX_REDIRECTS = 3
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

ACCEPT = (
    "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8"
)


class CrawlError(RuntimeError):
    """수집 실패. 메시지가 `news_sources.last_error` 와 화면에 그대로 노출된다."""


@dataclass(slots=True)
class Fetched:
    status: int
    headers: httpx.Headers
    text: str
    final_url: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def _read_limited(response: httpx.Response) -> str:
    """
    2.5MB 상한을 걸고 본문을 읽는다. `content-length` 를 먼저 보되 그 값을 신뢰하지 않고
    스트리밍하면서도 센다(거짓 헤더 대응).
    """
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FEED_BYTES:
        raise CrawlError("피드 크기가 2.5MB를 초과합니다.")

    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_FEED_BYTES:
            response.close()
            raise CrawlError("피드 크기가 2.5MB를 초과합니다.")
        chunks.append(chunk)

    # TextDecoder() 와 같다: charset 을 보지 않고 UTF-8, 실패 문자는 U+FFFD.
    return b"".join(chunks).decode("utf-8", errors="replace")


def safe_fetch(
    client: httpx.Client,
    url: str,
    headers: dict[str, str] | None = None,
    *,
    deadline: float | None = None,
) -> Fetched:
    """
    리다이렉트를 손으로 따라가며 **매 홉마다** SSRF 가드를 다시 통과시킨다.
    httpx 의 `follow_redirects` 를 쓰면 그 검사가 빠진다.
    """
    if deadline is None:
        deadline = time.monotonic() + DEADLINE_SECONDS

    current = validate_source_url(url)
    request_headers = {"User-Agent": USER_AGENT, "Accept": ACCEPT, **(headers or {})}

    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CrawlError("응답 시간이 12초를 초과했습니다.")
        try:
            with client.stream(
                "GET", current, headers=request_headers, timeout=remaining
            ) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise CrawlError("리다이렉트 위치가 없습니다.")
                    current = validate_source_url(urljoin(current, location))
                    continue
                return Fetched(
                    status=response.status_code,
                    headers=response.headers,
                    text=_read_limited(response),
                    final_url=current,
                )
        except httpx.TimeoutException as reason:
            raise CrawlError("응답 시간이 12초를 초과했습니다.") from reason
        except httpx.HTTPError as reason:
            raise CrawlError(f"뉴스 소스에 연결하지 못했습니다: {reason}") from reason

    raise CrawlError("리다이렉트가 너무 많습니다.")


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def assert_robots_allowed(
    client: httpx.Client,
    url: str,
    cache: dict[str, str] | None = None,
    *,
    deadline: float | None = None,
) -> None:
    """
    robots.txt 를 확인한다. origin 단위로 캐시해 한 실행 안에서 같은 사이트를 여러 번
    묻지 않는다(캐시가 실행마다 새로 만들어져 판정이 자기 자신과 일관된다).
    """
    target = validate_source_url(url)
    origin = _origin(target)

    if cache is not None and origin in cache:
        if not robots_allows(cache[origin], target):
            raise CrawlError("이 URL은 사이트의 robots.txt에서 자동 수집을 허용하지 않습니다.")
        return

    fetched = safe_fetch(
        client, f"{origin}/robots.txt", {"Accept": "text/plain"}, deadline=deadline
    )
    if fetched.status in (401, 403):
        raise CrawlError("이 사이트의 robots.txt가 자동 수집을 허용하지 않습니다.")
    if fetched.status >= 500:
        raise CrawlError("robots.txt를 확인할 수 없어 이번 수집을 보류했습니다.")
    if not fetched.ok:
        # 404 등은 "규칙 없음"으로 본다. 빈 문자열을 캐시해 같은 실행에서 다시 묻지 않는다.
        if cache is not None:
            cache[origin] = ""
        return

    if cache is not None:
        cache[origin] = fetched.text
    if not robots_allows(fetched.text, target):
        raise CrawlError("이 URL은 사이트의 robots.txt에서 자동 수집을 허용하지 않습니다.")


def build_client() -> httpx.Client:
    """
    리다이렉트를 직접 따라가므로 `follow_redirects=False` 가 필수다.
    prefork 워커에서 모듈 레벨로 공유하면 소켓이 자식 간에 섞이므로 호출부가 생성한다.
    """
    return httpx.Client(follow_redirects=False, http2=False)


__all__ = [
    "MAX_FEED_BYTES",
    "USER_AGENT",
    "CrawlError",
    "Fetched",
    "InvalidSourceUrl",
    "assert_robots_allowed",
    "build_client",
    "safe_fetch",
]

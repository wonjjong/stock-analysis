"""
네트워크 계층 검증. 실제 HTTP 서버를 띄워 확인한다(모킹하면 리다이렉트 재검증과
스트리밍 상한 같은 실제 동작을 놓친다).

TS 픽스처 테스트에 없던 커버리지다 — 원본은 이 경로를 테스트하지 않았다.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from news.crawler.fetcher import (
    MAX_FEED_BYTES,
    CrawlError,
    assert_robots_allowed,
    build_client,
    safe_fetch,
)
from news.crawler.jsurl import InvalidSourceUrl

STATE: dict[str, object] = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # 테스트 출력을 조용하게
        pass

    def do_GET(self) -> None:
        path = self.path
        STATE.setdefault("requests", []).append(path)  # type: ignore[union-attr]

        if path == "/robots.txt":
            body = STATE.get("robots", "User-agent: *\nAllow: /")
            status = int(STATE.get("robots_status", 200))
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if status < 400:
                self.wfile.write(str(body).encode())
            return

        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.end_headers()
            return

        if path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", "/redirect-loop")
            self.end_headers()
            return

        if path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/x")
            self.end_headers()
            return

        if path == "/lying-length":
            payload = b"x" * (MAX_FEED_BYTES + 1024)
            self.send_response(200)
            self.send_header("Content-Length", "10")  # 거짓말
            self.end_headers()
            self.wfile.write(payload[:10])
            return

        if path == "/too-big-declared":
            self.send_response(200)
            self.send_header("Content-Length", str(MAX_FEED_BYTES + 1))
            self.end_headers()
            return

        if path == "/not-modified":
            if self.headers.get("If-None-Match") == '"v1"':
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("ETag", '"v1"')
            self.end_headers()
            self.wfile.write(b"<html>fresh</html>")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html>ok</html>")


@pytest.fixture(scope="module")
def server() -> object:
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()


@pytest.fixture
def base(server: HTTPServer) -> str:
    STATE.clear()
    # 127.0.0.1 은 SSRF 가드가 막으므로, 테스트에서는 가드를 우회하도록
    # localhost 대신 loopback 을 허용하는 별도 경로가 필요하다 → 아래 monkeypatch 사용.
    return f"http://127.0.0.1:{server.server_port}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> object:
    """
    SSRF 가드는 loopback 을 막는다(그게 정상이다). 네트워크 동작만 검증하기 위해
    테스트에서만 가드를 통과시킨다 — 가드 자체는 test_parity_urls.py 가 검증한다.
    """
    import news.crawler.fetcher as fetcher_module

    monkeypatch.setattr(fetcher_module, "validate_source_url", lambda value: value.strip())
    with build_client() as client:
        yield client


def test_follows_redirect(client: object, base: str) -> None:
    fetched = safe_fetch(client, f"{base}/redirect")
    assert fetched.status == 200
    assert fetched.final_url.endswith("/final")


def test_redirect_loop_is_stopped(client: object, base: str) -> None:
    with pytest.raises(CrawlError, match="리다이렉트가 너무 많습니다"):
        safe_fetch(client, f"{base}/redirect-loop")


def test_declared_size_over_limit_is_rejected(client: object, base: str) -> None:
    with pytest.raises(CrawlError, match=r"2\.5MB"):
        safe_fetch(client, f"{base}/too-big-declared")


def test_conditional_request_returns_304(client: object, base: str) -> None:
    first = safe_fetch(client, f"{base}/not-modified")
    assert first.status == 200
    assert first.headers.get("etag") == '"v1"'
    second = safe_fetch(client, f"{base}/not-modified", {"If-None-Match": '"v1"'})
    assert second.status == 304


def test_robots_disallow_blocks(client: object, base: str) -> None:
    STATE["robots"] = "User-agent: *\nDisallow: /"
    with pytest.raises(CrawlError, match=r"robots\.txt"):
        assert_robots_allowed(client, f"{base}/news", {})


def test_robots_allow_passes(client: object, base: str) -> None:
    STATE["robots"] = "User-agent: *\nAllow: /news\nDisallow: /"
    # 예외가 나지 않으면 통과다.
    assert_robots_allowed(client, f"{base}/news", {})


def test_robots_403_is_treated_as_disallow(client: object, base: str) -> None:
    STATE["robots_status"] = 403
    with pytest.raises(CrawlError, match="자동 수집을 허용하지 않습니다"):
        assert_robots_allowed(client, f"{base}/news", {})


def test_robots_500_holds_the_run(client: object, base: str) -> None:
    STATE["robots_status"] = 503
    with pytest.raises(CrawlError, match="보류"):
        assert_robots_allowed(client, f"{base}/news", {})


def test_robots_404_allows_and_caches(client: object, base: str) -> None:
    STATE["robots_status"] = 404
    cache: dict[str, str] = {}
    assert_robots_allowed(client, f"{base}/news", cache)
    assert cache and next(iter(cache.values())) == ""
    # 캐시가 있으면 같은 실행에서 다시 묻지 않는다.
    before = len(STATE.get("requests", []))  # type: ignore[arg-type]
    assert_robots_allowed(client, f"{base}/other", cache)
    assert len(STATE.get("requests", [])) == before  # type: ignore[arg-type]


def test_ssrf_guard_rejects_loopback_without_monkeypatch() -> None:
    """가드가 실제로 동작하는지(위 테스트들이 우회한 그 가드)."""
    with build_client() as raw_client, pytest.raises(InvalidSourceUrl):
        safe_fetch(raw_client, "http://127.0.0.1:1/x")

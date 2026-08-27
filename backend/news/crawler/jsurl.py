"""
URL 정규화. `app/lib/news-crawler.ts` 의 absoluteArticleUrl / absolutePageUrl /
pageNumber / isPrivateIpv4 / validateSourceUrl 이식.

## 왜 손으로 쓰는가

브라우저의 `URL` 은 WHATWG 규격이고 Python `urllib.parse` 는 RFC 3986 이다. 둘은 실제로
다르며 WHATWG 를 정확히 구현한 Python 라이브러리가 없다. 그리고 여기가 틀리면 조용히
망가진다 — `canonical_url` 이 조금이라도 다르게 정규화되면 다음 수집이 기존 기사를 유사
URL 로 재삽입하고, UNIQUE 인덱스가 그것을 중복으로 보지 못해 코퍼스가 두 배가 된다.

그래서 정답지(`tests/parity/expected.json` 의 urlsViaAnchors · sourceUrls)를 보고 맞춘다.
추측으로 쓰지 않는다.

## `urllib` 이 채워 주지 않는 것

1. 기본 포트 제거 — `urlsplit` 은 `:443` 을 보존한다
2. 빈 쿼리 `?` 보존 — `urlsplit` 은 `https://x/1` 과 `https://x/1?` 을 구별하지 못한다
3. 쿼리 재직렬화 시점 — WHATWG `searchParams.delete()` 는 쿼리 전체를 다시 쓴다. 삭제가
   없으면 원형이 그대로 남으므로(`%20` 이 `+` 로 바뀌지 않는다) 삭제 여부를 추적한다
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from .text import decode_xml

# 목록 페이지가 같은 기사를 섹션·캠페인 쿼리를 붙여 여러 번 내주므로, canonical_url
# 유일성 검사 전에 떼어낸다.
TRACKING_PARAMS = frozenset({
    "gclid", "fbclid", "igshid", "spm", "mc_cid", "mc_eid",
    "section", "ref", "referer", "referrer", "from", "cp", "input", "sid",
})

PAGE_PARAMS = ("page", "cp", "p", "pageno", "pageindex", "curpage")

# WHATWG 가 "special scheme" 이라 부르는 것들. 기본 포트와 호스트 정규화가 여기에만 적용된다.
_DEFAULT_PORTS = {"http": "80", "https": "443", "ws": "80", "wss": "443", "ftp": "21"}
_SPECIAL = frozenset({*_DEFAULT_PORTS, "file"})

_DIGITS = re.compile(r"^\d+$", re.ASCII)
_HEX_HOST = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE | re.ASCII)
_PAGE_IN_PATH = re.compile(r"/(\d{1,3})/?$", re.ASCII)
_PAGE_VALUE = re.compile(r"^\d{1,3}$", re.ASCII)

# 경로·쿼리에서 퍼센트 인코딩하지 않고 남길 문자. WHATWG 의 path/query 집합에 맞춘다.
_PATH_SAFE = "/:@!$&'()*+,;=~-._"
_QUERY_SAFE = "/:@!$'()*+,;=?~-._&"


class InvalidSourceUrl(ValueError):
    """등록할 수 없는 소스 URL. 메시지는 화면에 그대로 노출되므로 원본과 같아야 한다."""


def _encode_host(host: str) -> str:
    """비ASCII 호스트를 punycode 로. WHATWG 는 UTS-46, Python 내장 코덱은 IDNA2003 이지만
    한국어 도메인에서는 같은 결과를 낸다(정답지로 확인)."""
    if not host or host.isascii():
        return host.lower()
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        # 인코딩할 수 없는 호스트. JS `new URL` 은 이 경우 던지고 호출부가 "" 로 흘린다.
        raise InvalidSourceUrl("올바른 뉴스 URL을 입력해 주세요.") from None


def _percent_encode(value: str, safe: str) -> str:
    """이미 퍼센트 인코딩된 부분은 건드리지 않고 비ASCII만 인코딩한다."""
    if value.isascii():
        return value
    return quote(value, safe=safe, encoding="utf-8")


def _split_query(query: str) -> list[tuple[str, str]]:
    """WHATWG application/x-www-form-urlencoded 파싱. `+` 는 공백이다."""
    pairs: list[tuple[str, str]] = []
    for chunk in query.split("&"):
        if not chunk:
            continue
        name, _, raw = chunk.partition("=")
        pairs.append((unquote(name.replace("+", " ")), unquote(raw.replace("+", " "))))
    return pairs


def _join_query(pairs: list[tuple[str, str]]) -> str:
    """공백은 `+`, 그 외 예약문자는 퍼센트 인코딩. WHATWG 직렬화와 같다."""
    def enc(part: str) -> str:
        return quote(part, safe="*-._", encoding="utf-8").replace("%20", "+")

    return "&".join(f"{enc(name)}={enc(value)}" for name, value in pairs)


def _remove_dot_segments(path: str) -> str:
    """
    RFC 3986 5.2.4. `urljoin` 은 상대 참조를 합칠 때만 이걸 적용하고 이미 절대인 참조는
    그대로 둔다. WHATWG `URL` 은 **항상** 정규화하므로(`https://x/a/../b` → `/b`) 직접 한다.
    """
    if "." not in path:
        return path
    out: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if out and out[-1] != "":
                out.pop()
            continue
        out.append(segment)
    normalized = "/".join(out)
    # 원문이 `/` 로 끝났거나 마지막 세그먼트가 점이었으면 슬래시를 유지한다.
    if path.endswith(("/.", "/..")) and not normalized.endswith("/"):
        normalized += "/"
    return normalized or "/"


def _had_query(text: str, base_url: str) -> bool:
    """
    원문에 `?` 가 있었는지. `urljoin` 은 빈 쿼리를 버리므로 결과 문자열로는 알 수 없다.

    WHATWG 규칙: 참조에 쿼리가 있으면 그것을, 참조가 비었거나 프래그먼트만이면 base 의
    쿼리를 물려받는다.
    """
    ref = text.split("#", 1)[0]
    if "?" in ref:
        return True
    if ref == "":
        return "?" in base_url.split("#", 1)[0]
    return False


def _normalize(value: str, base_url: str, *, strip_tracking: bool) -> str:
    """JS `new URL(value, base)` + `url.hash = ""` + (선택) 추적 쿼리 제거 + toString()."""
    text = decode_xml(value).strip()
    joined = urljoin(base_url, text)
    parts = urlsplit(joined)
    scheme = parts.scheme.lower()

    if scheme not in _SPECIAL:
        # javascript:, mailto: 같은 비특수 스킴은 JS 도 경로를 건드리지 않는다.
        # 프래그먼트만 떼고 그대로 돌려준다.
        return urlunsplit((scheme, parts.netloc, parts.path, parts.query, ""))

    host = _encode_host(parts.hostname or "")
    port = parts.port
    netloc = host
    if port is not None and str(port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"
    # IPv6 리터럴은 hostname 이 대괄호를 벗긴 값을 주므로 되돌린다.
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]" + (f":{port}" if port is not None
                                and str(port) != _DEFAULT_PORTS.get(scheme) else "")

    path = _remove_dot_segments(parts.path)
    path = _percent_encode(path, _PATH_SAFE) or ("/" if netloc else "")

    had_question = _had_query(text, base_url)
    query = parts.query
    deleted = False

    if strip_tracking and query:
        pairs = _split_query(query)
        kept = [
            (name, value) for name, value in pairs
            if not (name.startswith("utm_") or name.lower() in TRACKING_PARAMS)
        ]
        deleted = len(kept) != len(pairs)
        if deleted:
            query = _join_query(kept)

    if deleted and not query:
        # searchParams 가 비면 WHATWG 는 쿼리를 null 로 만들어 `?` 를 지운다.
        return urlunsplit((scheme, netloc, path, "", ""))
    if not query and had_question:
        # 원래 비어 있던 `?` 는 그대로 남는다.
        return urlunsplit((scheme, netloc, path, "", "")) + "?"
    return urlunsplit((scheme, netloc, path, _percent_encode(query, _QUERY_SAFE), ""))


def absolute_article_url(value: str, base_url: str) -> str:
    """기사 URL을 절대화하고 추적 쿼리를 떼어낸다. 실패하면 빈 문자열(원본과 같음)."""
    try:
        return _normalize(value, base_url, strip_tracking=True)
    except (ValueError, UnicodeError):
        return ""


def absolute_page_url(value: str, base_url: str) -> str:
    """목록 페이지 URL. 추적 쿼리를 떼지 않는다(페이지 파라미터가 거기 섞여 있다)."""
    try:
        return _normalize(value, base_url, strip_tracking=False)
    except (ValueError, UnicodeError):
        return ""


def page_number(value: str) -> int:
    """목록 URL에서 페이지 번호를 읽는다. 못 읽으면 1."""
    try:
        parts = urlsplit(value)
        if not parts.scheme:
            return 1
        for name, raw in _split_query(parts.query):
            if name.lower() in PAGE_PARAMS and _PAGE_VALUE.match(raw):
                return int(raw)
        match = _PAGE_IN_PATH.search(parts.path)
        return int(match.group(1)) if match else 1
    except ValueError:
        return 1


def is_private_ipv4(hostname: str) -> bool:
    parts = hostname.split(".")
    if len(parts) != 4 or any(not _DIGITS.match(part) for part in parts):
        return False
    nums = [int(part) for part in parts]
    if any(value < 0 or value > 255 for value in nums):
        return True
    return (
        nums[0] in (10, 127, 0)
        or (nums[0] == 169 and nums[1] == 254)
        or (nums[0] == 172 and 16 <= nums[1] <= 31)
        or (nums[0] == 192 and nums[1] == 168)
        or nums[0] >= 224
    )


def validate_source_url(value: str) -> str:
    """
    등록 가능한 소스 URL인지 검사하고 정규화한 값을 돌려준다.

    이식하면서 **강화하지 않는다.** DNS 해석 결과 검사와 IPv6 범위 검사는 원본에 없는
    추가 방어인데, 동작이 달라지면 동일성 diff 를 해석할 수 없게 된다. 하드닝은 이식이
    끝난 뒤 별도 작업으로 한다.
    """
    text = value.strip()
    parts = urlsplit(text)
    # JS `new URL(value)` 은 스킴만 있으면 성공하므로, 스킴 검사가 먼저다.
    # `file:///etc/passwd` 는 netloc 이 비어 있지만 "올바른 URL" 이고 프로토콜에서 걸린다.
    if not parts.scheme:
        raise InvalidSourceUrl("올바른 뉴스 URL을 입력해 주세요.")
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidSourceUrl("HTTP 또는 HTTPS URL만 등록할 수 있습니다.")
    if not parts.netloc:
        raise InvalidSourceUrl("올바른 뉴스 URL을 입력해 주세요.")

    try:
        raw_host = parts.hostname or ""
    except ValueError:
        raise InvalidSourceUrl("올바른 뉴스 URL을 입력해 주세요.") from None

    # JS 의 url.hostname 은 IPv6 를 대괄호째 돌려주므로 `host.includes(":")` 가 걸린다.
    # Python 은 대괄호를 벗기므로, 원문에서 대괄호를 확인해 같은 판정을 만든다.
    host = raw_host.lower().rstrip(".")
    bracketed = "[" in parts.netloc

    if (
        parts.username
        or parts.password
        or not host
        or bracketed
        or ":" in host
        or host == "localhost"
        or host.endswith(".local")
        or host.endswith(".internal")
        or _DIGITS.match(host)
        or _HEX_HOST.match(host)
        or is_private_ipv4(host)
    ):
        raise InvalidSourceUrl("내부 네트워크 주소는 등록할 수 없습니다.")

    return _normalize(text, text, strip_tracking=False)

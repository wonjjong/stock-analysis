import hashlib
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
import httpx
import trafilatura


@dataclass(frozen=True)
class CrawledArticle:
    canonical_url: str
    title: str
    publisher: str
    cleaned_text: str
    fetched_at: datetime
    content_hash: str


def canonicalize(url: str) -> str:
    parts = urlsplit(url)
    query = "&".join(item for item in parts.query.split("&") if item and not item.lower().startswith(("utm_", "fbclid=")))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


async def robots_allowed(client: httpx.AsyncClient, url: str, user_agent: str) -> bool:
    parts = urlsplit(url); robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    response = await client.get(robots_url, follow_redirects=True)
    if response.status_code >= 400: return False
    parser = urllib.robotparser.RobotFileParser(); parser.parse(response.text.splitlines())
    return parser.can_fetch(user_agent, url)


async def fetch_article(url: str, user_agent: str, publisher: str = "unknown") -> CrawledArticle:
    normalized = canonicalize(url)
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": user_agent}) as client:
        if not await robots_allowed(client, normalized, user_agent): raise PermissionError("robots.txt disallows crawling")
        response = await client.get(normalized, follow_redirects=True); response.raise_for_status()
    text = trafilatura.extract(response.text, include_comments=False, include_tables=False, favor_precision=True)
    if not text: raise ValueError("article body extraction failed")
    title = trafilatura.extract_metadata(response.text).title or normalized
    digest = hashlib.sha256(text.encode()).hexdigest(); now = datetime.now(timezone.utc)
    return CrawledArticle(normalized, title, publisher, text, now, digest)

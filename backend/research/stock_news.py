"""종목 뉴스의 검색 조건, 선별, 중복 제거와 점수화. 외부 시스템에 의존하지 않는다."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from news.crawler.analysis import analyze_news_locally
from news.crawler.jsurl import absolute_article_url
from news.crawler.symbols import lookup_symbol, match_symbols, occurrences
from research.analysis import Evidence


@dataclass(frozen=True, slots=True)
class StockNewsQuery:
    symbol: str
    market: str
    company: str
    aliases: tuple[str, ...]
    since: datetime
    until: datetime

    def __post_init__(self):
        if not self.symbol or self.market not in {"KR", "US"}:
            raise ValueError("종목과 시장이 필요합니다.")
        if self.since.tzinfo is None or self.until.tzinfo is None or self.since >= self.until:
            raise ValueError("검색 기간은 시간대가 있는 오름차순 시각이어야 합니다.")

    @property
    def terms(self) -> tuple[str, ...]:
        entry = lookup_symbol(self.symbol)
        terms = (self.company, *self.aliases, *(entry.aliases if entry else ()), self.symbol)
        return tuple(dict.fromkeys(term.strip() for term in terms if term.strip()))


@dataclass(frozen=True, slots=True)
class NewsItem:
    evidence: Evidence
    provider: str
    sentiment_score: int | None = None

    def __post_init__(self):
        if self.sentiment_score is not None and (
            isinstance(self.sentiment_score, bool) or not 0 <= self.sentiment_score <= 100
        ):
            raise ValueError("뉴스 감성 점수는 0~100입니다.")


class StockNewsSearchPort(Protocol):
    provider: str

    def search(self, query: StockNewsQuery) -> tuple[NewsItem, ...]: ...


@dataclass(frozen=True, slots=True)
class NewsProviderStatus:
    provider: str
    status: str = "success"
    fetched: int = 0
    accepted: int = 0
    cached: bool = False
    detail: str = ""


@dataclass(frozen=True, slots=True)
class StockNewsContext:
    items: tuple[NewsItem, ...] = ()
    providers: tuple[NewsProviderStatus, ...] = ()

    @property
    def evidence(self) -> list[Evidence]:
        return [item.evidence for item in self.items]

    @property
    def sentiment_scores(self) -> list[int]:
        return [item.sentiment_score for item in self.items if item.sentiment_score is not None]

    @property
    def data_gaps(self) -> list[str]:
        gaps = [f"{s.provider} 뉴스 {s.status}: {s.detail}" for s in self.providers
                if s.status in {"error", "unavailable"}]
        if not self.items:
            gaps.append("최근 30일의 종목 관련 뉴스 근거를 확보하지 못했습니다.")
        return gaps

    def as_dict(self) -> dict:
        return {"providers": [asdict(s) for s in self.providers], "count": len(self.items),
                "periodDays": 30, "cacheTtlSeconds": 1200, "dataGaps": self.data_gaps}


def _relevance(query: StockNewsQuery, evidence: Evidence) -> int:
    title, summary = evidence.title, evidence.summary
    text = f"{title} {summary}"
    # 기존 사전의 긴 별칭 우선 규칙으로 카카오뱅크→카카오 같은 오탐을 막는다.
    entry = lookup_symbol(query.symbol)
    if (entry and not any(m.symbol == entry.symbol for m in match_symbols(title, summary))
            and any(occurrences(text, term) for term in entry.aliases)):
        return 0
    matches = [term for term in query.terms if occurrences(text, term)]
    # A, ON, ARM 같은 짧은 영문 티커만으로 일반 단어 기사를 채택하지 않는다.
    matches = [term for term in matches if not (
        term.upper() == query.symbol and term.isalpha() and len(term) <= 3
    ) or re.search(rf"(?:\$|NASDAQ[:\s]+|NYSE[:\s]+){re.escape(term)}\b", text, re.I)]
    return max((2 if occurrences(title, term) else 1 for term in matches), default=0)


def select_news(query: StockNewsQuery, items: list[NewsItem],
                statuses: list[NewsProviderStatus]) -> StockNewsContext:
    unique: dict[str, tuple[int, datetime, NewsItem]] = {}
    for item in items:
        evidence = item.evidence
        try:
            observed = datetime.fromisoformat(evidence.observed_at.replace("Z", "+00:00"))
            if observed.tzinfo is None or not query.since <= observed <= query.until:
                continue
        except (ValueError, TypeError):
            continue
        relevance = _relevance(query, evidence)
        if not relevance:
            continue
        url = absolute_article_url(evidence.url, evidence.url) if evidence.url else ""
        if url and urlsplit(url).scheme not in {"http", "https"}:
            url = ""
        key = url or re.sub(r"[\W_]+", "", evidence.title.casefold())
        if not key:
            continue
        previous = unique.get(key)
        if previous and not (item.provider == "DB" and item.sentiment_score is not None
                             and previous[2].provider != "DB"):
            continue
        score = item.sentiment_score
        if score is None:
            score = int(analyze_news_locally(
                f"{evidence.title}. {evidence.summary}", query.symbol, query.company
            )["sentimentScore"])
        evidence = replace(evidence, url=url, id="stock-news:" + hashlib.sha256(
            key.encode()).hexdigest()[:32])
        unique[key] = (relevance, observed, replace(item, evidence=evidence, sentiment_score=score))
    selected = tuple(row[2] for row in sorted(
        unique.values(), key=lambda row: (-row[0], -row[1].timestamp(), row[2].evidence.id)
    )[:12])
    return StockNewsContext(selected, tuple(replace(
        status, accepted=sum(item.provider == status.provider for item in selected)
    ) for status in statuses))

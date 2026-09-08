"""저장 기사와 시장별 검색 포트를 결합하는 종목 뉴스 유스케이스."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Q

from news.models import NewsArticle
from research.analysis import Evidence
from research.services.company_index import CompanyIndexError
from research.services.kis_index import kis_index
from research.services.news_search import (
    GdeltNewsSearch,
    NaverNewsSearch,
    NewsSearchError,
    NewsSearchUnavailable,
)
from research.services.sec_index import resolve_us_company
from research.stock_news import (
    NewsItem,
    NewsProviderStatus,
    StockNewsContext,
    StockNewsQuery,
    StockNewsSearchPort,
    select_news,
)
from research.symbols import route_symbol


def build_news_query(symbol: str, company: str, now: datetime) -> StockNewsQuery:
    route = route_symbol(symbol)
    aliases = ()
    try:
        ref = kis_index.resolve(route.base) if route.market == "KR" else resolve_us_company(route.base)
        aliases = tuple(value for value in (ref.name, ref.name_en, *ref.aliases) if value)
    except CompanyIndexError:
        pass  # 시세의 회사명과 내장 사전으로 계속 검색한다.
    return StockNewsQuery(route.base, route.market, company, aliases, now - timedelta(days=30), now)


def stored_news(query: StockNewsQuery) -> tuple[NewsItem, ...]:
    rows = NewsArticle.objects.filter(
        Q(symbols__symbol__in=[query.symbol, f"{query.symbol}.KS", f"{query.symbol}.KQ"]),
        published_at__gte=query.since, published_at__lte=query.until,
    ).select_related("source", "insight").distinct().order_by("-published_at", "-id")[:50]
    result = []
    for article in rows:
        insight = getattr(article, "insight", None)
        result.append(NewsItem(Evidence(
            id=f"news:{article.pk}", kind="news", title=article.title[:300],
            source=article.source.name, observed_at=article.published_at.isoformat(),
            available_at=article.collected_at.isoformat(),
            summary=(insight.summary if insight else article.excerpt)[:800],
            url=article.canonical_url,
        ), "DB", insight.sentiment_score if insight else None))
    return tuple(result)


def collect_stock_news(
    symbol: str, company: str, yahoo: list[Evidence], *, yahoo_error: str = "",
    now: datetime | None = None, search: StockNewsSearchPort | None = None,
    yahoo_cached: bool = False,
) -> StockNewsContext:
    now = now or datetime.now(UTC)
    query = build_news_query(symbol, company, now)
    search = search or (NaverNewsSearch() if query.market == "KR" else GdeltNewsSearch())
    statuses = []
    items = []
    try:
        stored = stored_news(query)
        items.extend(stored)
        statuses.append(NewsProviderStatus("DB", fetched=len(stored)))
    except DatabaseError:
        statuses.append(NewsProviderStatus("DB", "error", detail="저장 뉴스 조회 실패"))
    items.extend(NewsItem(e, "Yahoo") for e in yahoo[:50])
    statuses.append(NewsProviderStatus("Yahoo", "error" if yahoo_error else "success",
                                       fetched=len(yahoo[:50]), detail=yahoo_error,
                                       cached=yahoo_cached))
    # 정확한 현재 시각을 키에 넣으면 매 요청이 miss이므로 기간 길이와 검색어로 식별한다.
    key = "research:stock-news:v1:" + sha256(
        repr((query.market, query.symbol, query.terms, 30, search.provider)).encode()
    ).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        external, status = cached
        status = replace(status, cached=True)
    else:
        try:
            external = search.search(query)
            status = NewsProviderStatus(search.provider, fetched=len(external))
        except NewsSearchUnavailable as reason:
            external = ()
            status = NewsProviderStatus(search.provider, "unavailable", detail=str(reason))
        except NewsSearchError as reason:
            external = ()
            status = NewsProviderStatus(search.provider, "error", detail=str(reason))
        # 오류·키 미설정은 캐시하지 않아 설정/공급자 복구가 즉시 반영된다.
        if status.status == "success":
            cache.set(key, (external, status), 1200)
    items.extend(external[:50])
    statuses.append(status)
    return select_news(query, items, statuses)

"""
화면. React 4개를 Django 템플릿으로 대체한다.

Spring MVC 와 같은 흐름이다 — 뷰가 모델을 채워 템플릿에 넘긴다. 이전 구조는 얇은 서버
껍데기가 HTML 을 내리고 브라우저가 다시 `fetch` 로 데이터를 받는 **왕복 두 번**이었고,
그래서 첫 화면에 "불러오는 중"이 보였다. 여기서는 한 번이다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from news.crawler.fetcher import CrawlError
from news.crawler.insights import rule_insight
from news.crawler.jsurl import InvalidSourceUrl
from news.crawler.llm_presets import LLM_PRESETS
from news.crawler.schedule import next_run_at
from news.crawler.symbols import match_symbols
from news.forms import AnalyzeForm, ArchiveFilterForm, ProviderForm, SourceForm
from news.models import InsightStatus, LlmProvider, NewsArticle, NewsCrawlRun, NewsSource
from news.services.ingest import crawl_source
from news.services.insights import insight_queue_stats, process_pending_insights
from news.services.llm import is_configured, provider_stats

logger = logging.getLogger(__name__)

RECENT_LIST_HOURS = 48
ARCHIVE_PAGE_SIZE = 30


def _now() -> datetime:
    return datetime.now(tz=UTC)


def healthz(request: HttpRequest) -> JsonResponse:
    """DB 연결과 이식 대상 테이블 존재를 함께 확인한다."""
    from django.db import connection

    tables: dict[str, int | str] = {}
    try:
        with connection.cursor() as cursor:
            for name in ("news_sources", "news_articles", "news_insights", "news_article_symbols"):
                # 테이블명은 위 고정 목록에서만 오므로 f-string 이 안전하다.
                cursor.execute(f"SELECT count(*) FROM {name}")
                tables[name] = cursor.fetchone()[0]
        status = "ok"
    except Exception as reason:
        # 헬스체크는 무엇이 실패했는지 그대로 노출하는 것이 목적이다.
        status = "error"
        tables = {"error": str(reason)}
    return JsonResponse({"status": status, "tables": tables})


# ─────────────────────────────────────────────────────────────── 대시보드

def dashboard(request: HttpRequest) -> HttpResponse:
    """파이프라인 상태 한 화면. 리서치 엔진이 생기면 여기가 추천 목록이 된다."""
    since = _now() - timedelta(hours=RECENT_LIST_HOURS)
    queue = insight_queue_stats()
    return render(request, "news/dashboard.html", {
        "sources": NewsSource.objects.annotate(article_count=Count("articles")).order_by(
            "-is_active", "name"
        ),
        "recent_count": NewsArticle.objects.filter(published_at__gte=since).count(),
        "total_count": NewsArticle.objects.count(),
        "queue": queue,
        "providers": provider_stats(),
        "runs": NewsCrawlRun.objects.select_related("source")[:8],
        "top_symbols": (
            NewsArticle.objects.filter(published_at__gte=since)
            .values("symbols__company", "symbols__symbol")
            .exclude(symbols__company=None)
            .annotate(n=Count("id"))
            .order_by("-n")[:10]
        ),
    })


# ─────────────────────────────────────────────────────────────── 소스 관리

def sources(request: HttpRequest) -> HttpResponse:
    form = SourceForm()
    since = _now() - timedelta(hours=RECENT_LIST_HOURS)
    return render(request, "news/sources.html", {
        "form": form,
        "sources": NewsSource.objects.annotate(
            article_count=Count("articles", distinct=True),
            run_count=Count("runs", distinct=True),
        ).order_by("-is_active", "-created_at"),
        "recent": (
            NewsArticle.objects.select_related("source")
            .filter(published_at__gte=since)
            .order_by("-published_at")[:40]
        ),
        "window_hours": RECENT_LIST_HOURS,
    })


@require_POST
def source_create(request: HttpRequest) -> HttpResponse:
    """
    등록 후 **즉시 1회 수집**한다. 원본 동작이고, 등록한 URL 이 실제로 쓸모 있는지 그
    자리에서 알 수 있어야 하기 때문이다.
    """
    form = SourceForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
        return redirect("sources")

    data = form.cleaned_data
    url = data["url"]
    from urllib.parse import urlsplit

    now = _now()
    source, created = NewsSource.objects.get_or_create(
        url=url,
        defaults={
            "name": data["name"] or (urlsplit(url).hostname or url),
            "symbol": "GENERAL",
            "company": "시장 전체",
            "category": data["category"],
            "crawl_hour_kst": data["crawl_hour_kst"],
            "max_pages": data["max_pages"],
            "window_hours": data["window_hours"],
            "is_active": True,
            "last_status": "첫 수집 대기",
            "next_crawl_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )
    if not created:
        messages.warning(request, "이미 등록된 URL 입니다.")
        return redirect("sources")

    try:
        result = crawl_source(source.pk)
    except (CrawlError, InvalidSourceUrl) as reason:
        messages.warning(
            request, f"등록은 됐지만 첫 수집에 실패했습니다: {reason}"
        )
        return redirect("sources")

    messages.success(
        request,
        f"{source.name} 등록 — {result.fetched_count}건 확인, 신규 {result.inserted_count}건 저장",
    )
    return redirect("sources")


@require_POST
def source_action(request: HttpRequest, source_id: int, action: str) -> HttpResponse:
    source = NewsSource.objects.filter(pk=source_id).first()
    if source is None:
        messages.error(request, "뉴스 소스를 찾지 못했습니다.")
        return redirect("sources")

    now = _now()
    if action == "crawl":
        try:
            result = crawl_source(source.pk)
        except (CrawlError, InvalidSourceUrl) as reason:
            messages.error(request, f"{source.name}: {reason}")
        else:
            messages.success(
                request,
                f"{source.name}: {result.status} — {result.fetched_count}건 확인,"
                f" 신규 {result.inserted_count}건",
            )
    elif action == "toggle":
        NewsSource.objects.filter(pk=source.pk).update(
            is_active=not source.is_active,
            next_crawl_at=datetime.fromtimestamp(
                next_run_at(source.crawl_hour_kst, int(now.timestamp() * 1000)) / 1000, tz=UTC
            ),
            updated_at=now,
        )
        messages.success(
            request, f"{source.name} 을 {'중지' if source.is_active else '재개'}했습니다."
        )
    elif action == "delete":
        name = source.name
        source.delete()
        messages.success(request, f"{name} 과 연결된 기사를 모두 삭제했습니다.")
    else:
        messages.error(request, f"알 수 없는 동작: {action}")
    return redirect("sources")


# ─────────────────────────────────────────────────────────────── 기사 아카이브

def _archive_queryset(data: dict[str, Any]) -> QuerySet:
    articles = NewsArticle.objects.select_related("source").prefetch_related("symbols")
    if data.get("date_from"):
        articles = articles.filter(published_date_kst__gte=data["date_from"])
    if data.get("date_to"):
        articles = articles.filter(published_date_kst__lte=data["date_to"])
    if data.get("source"):
        articles = articles.filter(source_id=data["source"])
    if data.get("sentiment"):
        articles = articles.filter(sentiment=data["sentiment"])
    if data.get("symbol"):
        articles = articles.filter(symbols__symbol=data["symbol"]).distinct()
    if data.get("q"):
        query = data["q"]
        # keywords 는 jsonb 다. 예전 구현은 직렬화된 JSON 텍스트를 LIKE 로 훑어 배열 원소
        # 경계를 넘어 매칭됐다. ORM 으로는 그 실수를 할 수 없고, 키워드 정확 일치 필터는
        # `symbol` 파라미터처럼 별도로 두는 편이 낫다.
        articles = articles.filter(
            Q(title__icontains=query)
            | Q(excerpt__icontains=query)
            | Q(analysis_summary__icontains=query)
            | Q(insight__summary__icontains=query)
        )
    return articles.order_by("-published_at", "-id")


def archive(request: HttpRequest) -> HttpResponse:
    form = ArchiveFilterForm(request.GET or None)
    data = form.cleaned_data if form.is_valid() else {}
    articles = _archive_queryset(data)

    summary = articles.aggregate(
        total=Count("id"),
        positive=Count("id", filter=Q(sentiment="긍정")),
        negative=Count("id", filter=Q(sentiment="부정")),
        pending=Count("id", filter=Q(insight_status=InsightStatus.PENDING)),
    )
    page = Paginator(articles, ARCHIVE_PAGE_SIZE).get_page(request.GET.get("page"))

    return render(request, "news/archive.html", {
        "form": form,
        "page": page,
        "summary": summary,
        "sources": NewsSource.objects.annotate(article_count=Count("articles")).order_by("name"),
        "top_symbols": (
            NewsArticle.objects.values("symbols__symbol", "symbols__company")
            .exclude(symbols__symbol=None)
            .annotate(n=Count("id"))
            .order_by("-n")[:30]
        ),
        "has_filters": any(data.get(key) for key in
                           ("q", "date_from", "date_to", "source", "sentiment", "symbol")),
    })


@require_POST
def run_insights(request: HttpRequest) -> HttpResponse:
    limit = min(50, max(1, int(request.POST.get("limit") or 12)))
    summary = process_pending_insights(limit)
    if not summary.picked:
        messages.info(request, "대기 중인 기사가 없습니다.")
    else:
        messages.success(
            request,
            f"{summary.picked}건 중 {summary.done}건 완료"
            f" (LLM {summary.llm} · 규칙 {summary.rule} · 실패 {summary.failed})",
        )
    return redirect(request.POST.get("next") or reverse("archive"))


# ─────────────────────────────────────────────────────────────── AI 공급자

def providers(request: HttpRequest) -> HttpResponse:
    return render(request, "news/providers.html", {
        "form": ProviderForm(),
        "providers": LlmProvider.objects.order_by("priority", "id"),
        "presets": LLM_PRESETS,
        "stats": provider_stats(),
        "now": _now(),
    })


@require_POST
def provider_create(request: HttpRequest) -> HttpResponse:
    form = ProviderForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
        return redirect("providers")

    data = form.cleaned_data
    now = _now()
    _, created = LlmProvider.objects.get_or_create(
        name=data["name"],
        defaults={
            "base_url": data["base_url"],
            "model": data["model"],
            "api_key": data["api_key"],
            "priority": data["priority"],
            "daily_limit": data["daily_limit"],
            "is_active": True,
            "last_status": "대기",
            "created_at": now,
            "updated_at": now,
        },
    )
    if created:
        messages.success(request, f"{data['name']} 을 등록했습니다.")
    else:
        messages.warning(request, "같은 이름의 공급자가 이미 있습니다.")
    return redirect("providers")


@require_POST
def provider_action(request: HttpRequest, provider_id: int, action: str) -> HttpResponse:
    provider = LlmProvider.objects.filter(pk=provider_id).first()
    if provider is None:
        messages.error(request, "공급자를 찾지 못했습니다.")
        return redirect("providers")

    now = _now()
    if action == "toggle":
        LlmProvider.objects.filter(pk=provider.pk).update(
            is_active=not provider.is_active, updated_at=now
        )
        messages.success(
            request, f"{provider.name} 을 {'중지' if provider.is_active else '재개'}했습니다."
        )
    elif action == "clear-cooldown":
        LlmProvider.objects.filter(pk=provider.pk).update(
            cooldown_until=None, last_error=None, last_status="대기", updated_at=now
        )
        messages.success(request, f"{provider.name} 의 쿨다운을 해제했습니다.")
    elif action == "test":
        _test_provider(request, provider)
    elif action == "delete":
        name = provider.name
        provider.delete()
        messages.success(request, f"{name} 을 삭제했습니다.")
    else:
        messages.error(request, f"알 수 없는 동작: {action}")
    return redirect("providers")


def _test_provider(request: HttpRequest, provider: LlmProvider) -> None:
    """실제로 한 번 호출해 본다 — 모델명과 한도는 공급자가 자주 바꾼다."""
    import httpx

    from news.crawler.llm import LlmConfig, LlmError, llm_json, timeout_ms

    config = LlmConfig(
        provider.base_url.rstrip("/"), provider.api_key, provider.model, timeout_ms()
    )
    try:
        with httpx.Client() as client:
            llm_json(
                client, config,
                "너는 테스트 응답기다. 반드시 {\"ok\": true} 만 출력한다.",
                "연결 확인",
            )
    except LlmError as reason:
        messages.error(request, f"{provider.name}: {reason.kind} — {reason}")
        return
    except Exception as reason:
        # 연결 확인은 어떤 실패든 화면에 그대로 보여 준다.
        messages.error(request, f"{provider.name}: 호출 실패 — {reason}")
        return
    messages.success(request, f"{provider.name}: 정상 응답을 받았습니다.")


# ─────────────────────────────────────────────────────────────── 즉석 분석

def lab(request: HttpRequest) -> HttpResponse:
    """
    기사 본문을 붙여넣어 결과를 본다. 저장하지 않는다 — 규칙 엔진과 LLM 이 무엇을 뽑는지
    확인하는 용도다.
    """
    result = None
    symbols: list = []
    if request.method == "POST":
        form = AnalyzeForm(request.POST)
        if form.is_valid():
            title = form.cleaned_data["title"]
            body = form.cleaned_data["body"]
            base = rule_insight(title, body)
            symbols = match_symbols(title, body)
            result = base

            if form.cleaned_data["use_llm"] and is_configured():
                import json as _json

                from news.crawler.insights import LLM_BODY_LIMIT, SYSTEM_PROMPT, llm_insight
                from news.services.llm import llm_json_with_failover

                chain = llm_json_with_failover(
                    SYSTEM_PROMPT,
                    _json.dumps(
                        {"title": title, "article": body[:LLM_BODY_LIMIT]}, ensure_ascii=False
                    ),
                )
                if chain.parsed is not None and chain.provider_name:
                    result = llm_insight(
                        chain.parsed if isinstance(chain.parsed, dict) else {},
                        base, chain.provider_name, "",
                    )
                else:
                    detail = ", ".join(
                        f"{a.name}({a.kind})" for a in chain.attempts
                    ) or "쓸 수 있는 공급자가 없습니다"
                    messages.warning(request, f"AI 분석 실패 — 규칙 기반 결과입니다. {detail}")
    else:
        form = AnalyzeForm()

    return render(request, "news/lab.html", {
        "form": form,
        "result": result,
        "symbols": symbols,
        "llm_configured": is_configured(),
    })

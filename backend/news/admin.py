"""
운영 조회용 Admin.

지금까지 psql 로 보던 것들을 화면으로 옮긴다 — 크롤이 왜 실패했나, 인사이트 큐가 얼마나
밀렸나, 공급자별 사용량이 얼마나 남았나.

모델이 `managed = False` 라 스키마는 여전히 drizzle 소유다. Admin 은 읽고 일부만 고친다.
관측용 테이블(수집 실행·본문 분석)은 **읽기 전용**으로 둔다 — 손으로 고칠 값이 아니고,
고치면 크롤 동작 여부 판단이 흐려진다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from news.models import (
    LlmProvider,
    NewsArticle,
    NewsArticleSymbol,
    NewsCrawlRun,
    NewsInsight,
    NewsSource,
)

admin.site.site_header = "Signalist 운영"
admin.site.site_title = "Signalist"
admin.site.index_title = "뉴스 파이프라인"


class ReadOnlyAdmin(admin.ModelAdmin):
    """관측용 테이블. 손으로 고치면 파이프라인 상태 판단이 흐려진다."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


def _status_chip(value: str) -> str:
    colors = {
        "완료": "#1E7A4C", "정상": "#1E7A4C",
        "오류": "#B4232A", "인증 오류": "#B4232A",
        "한도 초과": "#96601A", "요청 오류": "#96601A", "일시 오류": "#96601A",
        "실행 중": "#0F766E", "대기": "#7C868C",
        "변경 없음": "#7C868C", "새 기사 없음": "#7C868C", "제외": "#7C868C",
    }
    color = colors.get(value, "#4A5257")
    return format_html(
        '<span style="color:{};font-weight:600">{}</span>', color, value or "—"
    )


@admin.register(NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "active_chip", "status_chip", "crawl_hour_kst",
        "window_hours", "max_pages", "article_count", "next_crawl_at", "last_error_short",
    )
    list_filter = ("is_active", "category", "last_status")
    search_fields = ("name", "url", "resolved_url")
    ordering = ("-is_active", "name")
    # 스키마는 drizzle 소유다. 운영자가 조정할 값만 편집 대상으로 둔다.
    fields = (
        "name", "url", "resolved_url", "category", "is_active",
        "crawl_hour_kst", "window_hours", "max_pages",
        "last_status", "last_error", "last_crawled_at", "next_crawl_at",
        "etag", "last_modified", "created_at", "updated_at",
    )
    readonly_fields = (
        "url", "resolved_url", "last_status", "last_error", "last_crawled_at",
        "etag", "last_modified", "created_at", "updated_at",
    )
    actions = ("crawl_now", "reset_schedule")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).annotate(_articles=Count("articles"))

    @admin.display(description="활성", boolean=True, ordering="is_active")
    def active_chip(self, obj: NewsSource) -> bool:
        return obj.is_active

    @admin.display(description="최근 상태", ordering="last_status")
    def status_chip(self, obj: NewsSource) -> str:
        return _status_chip(obj.last_status)

    @admin.display(description="기사", ordering="_articles")
    def article_count(self, obj: NewsSource) -> int:
        return getattr(obj, "_articles", 0)

    @admin.display(description="마지막 오류")
    def last_error_short(self, obj: NewsSource) -> str:
        return (obj.last_error or "")[:60]

    @admin.action(description="선택한 소스를 지금 수집")
    def crawl_now(self, request: HttpRequest, queryset: QuerySet) -> None:
        from news.crawler.fetcher import CrawlError
        from news.services.ingest import crawl_source

        for source in queryset:
            try:
                result = crawl_source(source.pk)
            except CrawlError as reason:
                self.message_user(request, f"{source.name}: {reason}", level="error")
                continue
            self.message_user(
                request,
                f"{source.name}: {result.status} — {result.fetched_count}건 확인,"
                f" 신규 {result.inserted_count}건",
            )

    @admin.action(description="다음 실행 시각을 지금으로 (곧 수집)")
    def reset_schedule(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(next_crawl_at=datetime.now(tz=UTC))
        self.message_user(request, f"{updated}개 소스를 다음 tick 에 수집하도록 했습니다.")


@admin.register(NewsCrawlRun)
class NewsCrawlRunAdmin(ReadOnlyAdmin):
    list_display = (
        "started_at", "source", "status_chip", "fetched_count", "inserted_count",
        "duration", "error_short",
    )
    list_filter = ("status", "source")
    list_select_related = ("source",)
    date_hierarchy = "started_at"
    ordering = ("-started_at",)

    @admin.display(description="상태", ordering="status")
    def status_chip(self, obj: NewsCrawlRun) -> str:
        return _status_chip(obj.status)

    @admin.display(description="소요")
    def duration(self, obj: NewsCrawlRun) -> str:
        if not obj.completed_at:
            return "진행 중"
        seconds = (obj.completed_at - obj.started_at).total_seconds()
        return f"{seconds:.1f}초"

    @admin.display(description="오류")
    def error_short(self, obj: NewsCrawlRun) -> str:
        return (obj.error or "")[:70]


class SymbolInline(admin.TabularInline):
    model = NewsArticleSymbol
    extra = 0
    can_delete = False
    fields = ("symbol", "company", "market", "sector", "mentions", "relevance")
    readonly_fields = fields


@admin.register(NewsArticle)
class NewsArticleAdmin(ReadOnlyAdmin):
    list_display = (
        "published_date_kst", "title_short", "source", "insight_chip",
        "sentiment_chip", "materiality", "symbol_names",
    )
    list_filter = ("insight_status", "sentiment", "materiality", "source")
    search_fields = ("title", "excerpt", "canonical_url")
    list_select_related = ("source",)
    date_hierarchy = "published_at"
    ordering = ("-published_at",)
    inlines = (SymbolInline,)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).prefetch_related("symbols")

    @admin.display(description="제목", ordering="title")
    def title_short(self, obj: NewsArticle) -> str:
        return obj.title[:55]

    @admin.display(description="분석", ordering="insight_status")
    def insight_chip(self, obj: NewsArticle) -> str:
        return _status_chip(obj.insight_status)

    @admin.display(description="감성", ordering="sentiment_score")
    def sentiment_chip(self, obj: NewsArticle) -> str:
        return format_html("{} <small>{}</small>", obj.sentiment, obj.sentiment_score)

    @admin.display(description="종목")
    def symbol_names(self, obj: NewsArticle) -> str:
        return ", ".join(s.company for s in obj.symbols.all()[:3]) or "—"


@admin.register(NewsInsight)
class NewsInsightAdmin(ReadOnlyAdmin):
    list_display = (
        "article_title", "engine", "sentiment", "materiality", "body_chars",
        "keyword_preview", "attempts", "error_short", "updated_at",
    )
    list_filter = ("engine", "sentiment", "materiality", "impact_horizon")
    search_fields = ("summary", "article__title")
    list_select_related = ("article",)
    ordering = ("-updated_at",)

    @admin.display(description="기사")
    def article_title(self, obj: NewsInsight) -> str:
        return obj.article.title[:50]

    @admin.display(description="키워드")
    def keyword_preview(self, obj: NewsInsight) -> str:
        return ", ".join(obj.keywords[:4]) if obj.keywords else "—"

    @admin.display(description="오류")
    def error_short(self, obj: NewsInsight) -> str:
        return (obj.error or "")[:50]


@admin.register(LlmProvider)
class LlmProviderAdmin(admin.ModelAdmin):
    list_display = (
        "name", "priority", "active_chip", "model", "usage", "status_chip",
        "cooldown_left", "success_count", "failure_count", "key_hint",
    )
    list_filter = ("is_active", "last_status")
    ordering = ("priority", "id")
    fields = (
        "name", "base_url", "model", "api_key", "priority", "is_active", "daily_limit",
        "used_today", "usage_date_kst", "cooldown_until", "last_status", "last_error",
        "last_used_at", "success_count", "failure_count", "created_at", "updated_at",
    )
    readonly_fields = (
        "used_today", "usage_date_kst", "cooldown_until", "last_status", "last_error",
        "last_used_at", "success_count", "failure_count", "created_at", "updated_at",
    )
    actions = ("clear_cooldown", "reset_usage")

    @admin.display(description="활성", boolean=True, ordering="is_active")
    def active_chip(self, obj: LlmProvider) -> bool:
        return obj.is_active

    @admin.display(description="오늘 사용")
    def usage(self, obj: LlmProvider) -> str:
        limit = f"/{obj.daily_limit}" if obj.daily_limit else " (무제한)"
        return f"{obj.used_today}{limit}"

    @admin.display(description="상태", ordering="last_status")
    def status_chip(self, obj: LlmProvider) -> str:
        return _status_chip(obj.last_status)

    @admin.display(description="쿨다운")
    def cooldown_left(self, obj: LlmProvider) -> str:
        if not obj.cooldown_until:
            return "—"
        remaining = obj.cooldown_until - datetime.now(tz=UTC)
        if remaining.total_seconds() <= 0:
            return "만료"
        minutes = int(remaining.total_seconds() // 60)
        return f"{minutes // 60}시간 {minutes % 60}분" if minutes >= 60 else f"{minutes}분"

    @admin.display(description="키")
    def key_hint(self, obj: LlmProvider) -> str:
        """끝 네 글자만 노출한다. 화면과 API 응답 모두 같은 규칙이다."""
        return obj.masked_key

    @admin.action(description="쿨다운 해제 (지금 다시 시도)")
    def clear_cooldown(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(cooldown_until=None, last_error=None, last_status="대기")
        self.message_user(request, f"{updated}개 공급자의 쿨다운을 해제했습니다.")

    @admin.action(description="오늘 사용량 0으로")
    def reset_usage(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(used_today=0, usage_date_kst=None)
        self.message_user(request, f"{updated}개 공급자의 사용량을 초기화했습니다.")

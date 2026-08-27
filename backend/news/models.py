"""
기존 PostgreSQL 테이블에 대응하는 모델.

## 전부 `managed = False` 다

스키마 소유자는 TypeScript 쪽 drizzle(`db/schema.ts` → `drizzle/*.sql`)이다. 이식이
끝나고 TS 를 삭제할 때까지 Django 마이그레이션이 이 테이블을 만들거나 바꾸지 않는다.
한 테이블에 두 소유자를 두면 서로의 변경을 되돌린다.

TS 를 삭제하는 시점에 `managed = True` 로 바꾸고 `--fake-initial` 로 마이그레이션
이력을 맞춘다.
"""

from __future__ import annotations

from django.db import connection, models


class NewsArticleManager(models.Manager):
    """`insert_ignore` 를 제공한다."""

    # 컬럼 순서를 한 곳에 둔다. published_date_kst 는 DB 생성 열이라 빠진다.
    _COLUMNS = (
        "source_id", "symbol", "title", "canonical_url", "excerpt", "published_at",
        "content_hash", "sentiment", "sentiment_score", "materiality", "relevance",
        "event_type", "score_adjustment", "analysis_summary", "collected_at",
    )

    def insert_ignore(self, **values: object) -> int:
        """
        `INSERT … ON CONFLICT (canonical_url) DO NOTHING` 을 실행하고 **신규 저장 건수**를
        돌려준다.

        `bulk_create(ignore_conflicts=True)` 는 pk 도 개수도 주지 않는다. 그런데 이 숫자가
        `news_crawl_runs.inserted_count` 가 되고 화면에 "신규 N개 저장" 으로 보이며,
        크롤이 실제로 동작하는지 판단하는 유일한 관측 수단이다. 그래서 raw SQL 을 쓴다.
        """
        missing = set(self._COLUMNS) - set(values)
        if missing:
            raise ValueError(f"insert_ignore 에 빠진 컬럼: {sorted(missing)}")
        columns = ", ".join(f'"{name}"' for name in self._COLUMNS)
        placeholders = ", ".join(["%s"] * len(self._COLUMNS))
        params = [values[name] for name in self._COLUMNS]
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO "news_articles" ({columns}) VALUES ({placeholders})'
                " ON CONFLICT (canonical_url) DO NOTHING",
                params,
            )
            return cursor.rowcount or 0


class InsightStatus(models.TextChoices):
    PENDING = "대기", "대기"
    DONE = "완료", "완료"
    SKIPPED = "제외", "제외"
    ERROR = "오류", "오류"


class CrawlStatus(models.TextChoices):
    RUNNING = "실행 중", "실행 중"
    DONE = "완료", "완료"
    NOT_MODIFIED = "변경 없음", "변경 없음"
    EMPTY = "새 기사 없음", "새 기사 없음"
    ERROR = "오류", "오류"


class NewsSource(models.Model):
    name = models.TextField()
    url = models.TextField(unique=True)
    resolved_url = models.TextField(null=True, blank=True)
    symbol = models.TextField()
    company = models.TextField()
    category = models.TextField(default="종합")
    crawl_hour_kst = models.IntegerField(default=6)
    max_pages = models.IntegerField(default=1)
    window_hours = models.IntegerField(default=36)
    is_active = models.BooleanField(default=True)
    etag = models.TextField(null=True, blank=True)
    last_modified = models.TextField(null=True, blank=True)
    last_status = models.TextField(default="대기")
    last_error = models.TextField(null=True, blank=True)
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    next_crawl_at = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "news_sources"
        ordering = ["-is_active", "-created_at"]
        verbose_name = "뉴스 소스"
        verbose_name_plural = "뉴스 소스"

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"


class NewsArticle(models.Model):
    source = models.ForeignKey(
        NewsSource, on_delete=models.CASCADE, db_column="source_id", related_name="articles"
    )
    symbol = models.TextField()
    title = models.TextField()
    canonical_url = models.TextField(unique=True)
    excerpt = models.TextField(default="")
    published_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.TextField()
    sentiment = models.TextField()
    sentiment_score = models.IntegerField()
    materiality = models.TextField()
    relevance = models.IntegerField()
    event_type = models.TextField()
    score_adjustment = models.IntegerField()
    analysis_summary = models.TextField()
    collected_at = models.DateTimeField()
    # DB 생성 열이다. Django 는 읽기만 한다.
    published_date_kst = models.DateField(editable=False)
    insight_status = models.TextField(choices=InsightStatus, default=InsightStatus.PENDING)

    objects = NewsArticleManager()

    class Meta:
        managed = False
        db_table = "news_articles"
        ordering = ["-published_at", "-id"]
        verbose_name = "수집 기사"
        verbose_name_plural = "수집 기사"

    def __str__(self) -> str:
        return self.title[:60]


class NewsInsight(models.Model):
    article = models.OneToOneField(
        NewsArticle, on_delete=models.CASCADE, db_column="article_id", related_name="insight"
    )
    summary = models.TextField(default="")
    keywords = models.JSONField(default=list)
    sectors = models.JSONField(default=list)
    evidence = models.JSONField(default=list)
    sentiment = models.TextField(default="중립")
    sentiment_score = models.IntegerField(default=50)
    materiality = models.TextField(default="낮음")
    event_type = models.TextField(default="산업·시장동향")
    impact_horizon = models.TextField(default="당일")
    market_view = models.TextField(default="")
    body_chars = models.IntegerField(default=0)
    engine = models.TextField(default="규칙 기반")
    model = models.TextField(default="")
    attempts = models.IntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "news_insights"
        verbose_name = "본문 분석"
        verbose_name_plural = "본문 분석"

    def __str__(self) -> str:
        return f"{self.article_id}: {self.summary[:40]}"


class NewsArticleSymbol(models.Model):
    article = models.ForeignKey(
        NewsArticle, on_delete=models.CASCADE, db_column="article_id", related_name="symbols"
    )
    symbol = models.TextField()
    company = models.TextField()
    market = models.TextField(default="KR")
    sector = models.TextField(default="")
    match_type = models.TextField(default="사전")
    mentions = models.IntegerField(default=1)
    relevance = models.IntegerField(default=50)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "news_article_symbols"
        ordering = ["-relevance"]
        verbose_name = "기사 종목"
        verbose_name_plural = "기사 종목"

    def __str__(self) -> str:
        return f"{self.company}({self.symbol})"


class NewsCrawlRun(models.Model):
    source = models.ForeignKey(
        NewsSource, on_delete=models.CASCADE, db_column="source_id", related_name="runs"
    )
    status = models.TextField(choices=CrawlStatus)
    fetched_count = models.IntegerField(default=0)
    inserted_count = models.IntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "news_crawl_runs"
        ordering = ["-started_at"]
        verbose_name = "수집 실행"
        verbose_name_plural = "수집 실행"

    def __str__(self) -> str:
        return f"{self.source_id} {self.status} {self.started_at:%m-%d %H:%M}"


class LlmProvider(models.Model):
    name = models.TextField(unique=True)
    base_url = models.TextField()
    model = models.TextField()
    api_key = models.TextField(default="")
    priority = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)
    daily_limit = models.IntegerField(default=0)
    used_today = models.IntegerField(default=0)
    usage_date_kst = models.DateField(null=True, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    last_status = models.TextField(default="대기")
    last_error = models.TextField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "llm_providers"
        ordering = ["is_active", "priority"]
        verbose_name = "AI 공급자"
        verbose_name_plural = "AI 공급자"

    def __str__(self) -> str:
        return f"{self.name} (우선순위 {self.priority})"

    @property
    def masked_key(self) -> str:
        """화면과 API 응답에는 끝 네 글자만 노출한다."""
        return f"…{self.api_key[-4:]}" if len(self.api_key) > 4 else "미설정"

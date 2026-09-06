"""
뉴스 파이프라인 모델.

## 스키마 소유자가 Django 로 넘어왔다

이식 중에는 `managed = False` 로 두어 drizzle(`db/schema.ts`)이 스키마를 소유했다. 한
테이블에 두 소유자를 두면 서로의 변경을 되돌리기 때문이다. TypeScript 를 삭제한 지금은
Django 마이그레이션이 소유한다.

이전 이력은 `--fake-initial` 로 맞췄다 — 테이블이 이미 존재하므로 첫 마이그레이션은
"이미 적용됨"으로 기록만 하고 DDL 을 실행하지 않는다. SQLite 시절과 Postgres 전환기의
drizzle 마이그레이션은 `docs/reference/` 에 보존돼 있다.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.db import connection, models
from django.db.models.functions import Cast, Coalesce

# drizzle 의 `serial` 은 32비트 integer 다. 프로젝트 기본값(BigAutoField)을 그대로 쓰면
# 마이그레이션이 bigint 를 만들어 기존 DB 와 어긋나고, `--fake-initial` 이 실제와 다른
# 스키마를 "적용됨"으로 기록해 거짓말이 된다. 기존 컬럼 타입에 맞춘다.
#
# 행 수가 21억에 근접하면 그때 bigint 로 올리는 별도 마이그레이션을 쓴다.

class NewsArticleManager(models.Manager):
    """`insert_ignore` 를 제공한다."""

    # 컬럼 순서를 한 곳에 둔다. published_date_kst 는 DB 생성 열이라 빠진다.
    #
    # insight_status 는 모델에 default 가 있지만 여기에 있어야 한다 — Django 의 default 는
    # 파이썬 쪽 값이라 DDL 에 DEFAULT 를 만들지 않는다. 이 raw SQL 은 ORM 을 우회하므로
    # 빼면 NOT NULL 위반으로 수집이 통째로 실패한다.
    _COLUMNS = (
        "source_id", "symbol", "title", "canonical_url", "excerpt", "published_at",
        "content_hash", "sentiment", "sentiment_score", "materiality", "relevance",
        "event_type", "score_adjustment", "analysis_summary", "collected_at",
        "insight_status",
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
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    url = models.TextField(unique=True)
    resolved_url = models.TextField(null=True, blank=True)
    symbol = models.TextField()
    company = models.TextField()
    category = models.TextField(default="종합")
    crawl_hour_kst = models.IntegerField(default=6)
    # 0 이면 하루 한 번(`crawl_hour_kst`), 양수면 그 분 주기로 돈다. 기본을 0 으로 둔 것은
    # 기존 소스의 동작을 바꾸지 않기 위해서다.
    crawl_interval_minutes = models.IntegerField(default=0)
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
        db_table = "news_sources"
        ordering = ["-is_active", "-created_at"]
        verbose_name = "뉴스 소스"
        verbose_name_plural = "뉴스 소스"
        indexes = [
            # 스케줄러의 "기한이 된 소스" 조회를 받친다.
            models.Index(fields=["is_active", "next_crawl_at"], name="news_src_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.category})"


class NewsArticle(models.Model):
    id = models.AutoField(primary_key=True)
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
    # DB 가 계산하는 생성 열이다. 앱이 쓰지 않는다.
    #
    # SQLite 시절에는 타임존을 아는 날짜 추출이 불가능해 앱이 직접 썼고, 빈 문자열로 남은
    # 과거 행 때문에 조회 쪽에서 COALESCE 로 되살려야 했다. DB 가 계산하면 그 부류의 행이
    # 아예 생기지 않는다.
    #
    # STORED 생성 열은 IMMUTABLE 식을 요구한다. `timezone(text, timestamptz)` 는
    # pg_proc 에서 IMMUTABLE 이다(`timestamptz::date` 는 TimeZone GUC 를 읽어 STABLE 이라
    # 쓸 수 없다).
    published_date_kst = models.GeneratedField(
        expression=Cast(
            models.Func(
                Coalesce("published_at", "collected_at"),
                models.Value("Asia/Seoul"),
                function="timezone",
                arg_joiner=" AT TIME ZONE ",
                template="(%(expressions)s)",
            ),
            output_field=models.DateField(),
        ),
        output_field=models.DateField(),
        db_persist=True,
    )
    insight_status = models.TextField(choices=InsightStatus, default=InsightStatus.PENDING)

    objects = NewsArticleManager()

    class Meta:
        db_table = "news_articles"
        ordering = ["-published_at", "-id"]
        verbose_name = "수집 기사"
        verbose_name_plural = "수집 기사"
        indexes = [
            models.Index(
                fields=["published_date_kst", "published_at"],
                name="news_art_pubdate_idx",
            ),
            models.Index(fields=["source", "collected_at"], name="news_art_src_coll_idx"),
            # 본문 분석 큐의 "대기 중인 기사" 조회를 받친다.
            models.Index(
                fields=["insight_status", "published_at"],
                name="news_art_queue_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title[:60]


class NewsInsight(models.Model):
    id = models.AutoField(primary_key=True)
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
        db_table = "news_insights"
        verbose_name = "본문 분석"
        verbose_name_plural = "본문 분석"
        indexes = [
            # 키워드·업종 정확 일치 필터를 인덱스로 받는다. `@>` 연산자만 이 인덱스를
            # 타고, `jsonb_exists()` 함수 형태는 Seq Scan 이 된다(실측).
            GinIndex(fields=["keywords"], name="news_insights_keywords_gin"),
            GinIndex(fields=["sectors"], name="news_insights_sectors_gin"),
        ]

    def __str__(self) -> str:
        return f"{self.article_id}: {self.summary[:40]}"


class NewsArticleSymbol(models.Model):
    id = models.AutoField(primary_key=True)
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
        db_table = "news_article_symbols"
        ordering = ["-relevance"]
        verbose_name = "기사 종목"
        verbose_name_plural = "기사 종목"
        constraints = [
            # 같은 기사에 같은 종목이 두 번 들어가지 않는다.
            models.UniqueConstraint(
                fields=["article", "symbol"], name="news_sym_article_symbol_uq"
            ),
        ]
        indexes = [
            models.Index(fields=["symbol", "created_at"], name="news_sym_symbol_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company}({self.symbol})"


class NewsCrawlRun(models.Model):
    id = models.AutoField(primary_key=True)
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
        db_table = "news_crawl_runs"
        ordering = ["-started_at"]
        verbose_name = "수집 실행"
        verbose_name_plural = "수집 실행"
        indexes = [
            models.Index(fields=["source", "started_at"], name="news_run_src_started_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} {self.status} {self.started_at:%m-%d %H:%M}"


class LlmProvider(models.Model):
    id = models.AutoField(primary_key=True)
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
        db_table = "llm_providers"
        ordering = ["is_active", "priority"]
        verbose_name = "AI 공급자"
        verbose_name_plural = "AI 공급자"
        indexes = [
            # 페일오버의 "쓸 수 있는 공급자" 조회를 받친다.
            models.Index(fields=["is_active", "priority"], name="llm_prov_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} (우선순위 {self.priority})"

    @property
    def masked_key(self) -> str:
        """화면과 API 응답에는 끝 네 글자만 노출한다."""
        return f"…{self.api_key[-4:]}" if len(self.api_key) > 4 else "미설정"

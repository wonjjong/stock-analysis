import { sql } from "drizzle-orm";
import { boolean, date, index, integer, jsonb, pgTable, serial, text, timestamp, uniqueIndex } from "drizzle-orm/pg-core";

// 모든 시각은 timestamptz로 저장한다. SQLite 시절에는 정수 밀리초였고, 타임존을 아는
// 날짜 추출이 불가능해 published_date_kst를 앱이 직접 써야 했다.
const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const newsSources = pgTable("news_sources", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  url: text("url").notNull(),
  resolvedUrl: text("resolved_url"),
  symbol: text("symbol").notNull(),
  company: text("company").notNull(),
  category: text("category").notNull().default("종합"),
  crawlHourKst: integer("crawl_hour_kst").notNull().default(6),
  maxPages: integer("max_pages").notNull().default(1),
  windowHours: integer("window_hours").notNull().default(36),
  isActive: boolean("is_active").notNull().default(true),
  etag: text("etag"),
  lastModified: text("last_modified"),
  lastStatus: text("last_status").notNull().default("대기"),
  lastError: text("last_error"),
  lastCrawledAt: ts("last_crawled_at"),
  nextCrawlAt: ts("next_crawl_at").notNull(),
  createdAt: ts("created_at").notNull(),
  updatedAt: ts("updated_at").notNull(),
}, (table) => [
  uniqueIndex("news_sources_url_unique").on(table.url),
  index("news_sources_due_idx").on(table.isActive, table.nextCrawlAt),
]);

export const newsArticles = pgTable("news_articles", {
  id: serial("id").primaryKey(),
  sourceId: integer("source_id").notNull().references(() => newsSources.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  title: text("title").notNull(),
  canonicalUrl: text("canonical_url").notNull(),
  excerpt: text("excerpt").notNull().default(""),
  publishedAt: ts("published_at"),
  contentHash: text("content_hash").notNull(),
  sentiment: text("sentiment").notNull(),
  sentimentScore: integer("sentiment_score").notNull(),
  materiality: text("materiality").notNull(),
  relevance: integer("relevance").notNull(),
  eventType: text("event_type").notNull(),
  scoreAdjustment: integer("score_adjustment").notNull(),
  analysisSummary: text("analysis_summary").notNull(),
  collectedAt: ts("collected_at").notNull(),
  // 앱이 쓰지 않는 생성 열이다. 예전에는 text NOT NULL DEFAULT ''였고 빈 문자열로 남은
  // 과거 행 때문에 조회 쪽에서 COALESCE로 KST 날짜를 되살려야 했다. DB가 계산하면
  // 그 부류의 행이 아예 생기지 않고 인덱스도 그대로 쓸 수 있다.
  // timezone(text, timestamptz)는 IMMUTABLE이라 STORED 생성 열에 쓸 수 있다.
  publishedDateKst: date("published_date_kst").generatedAlwaysAs(
    sql`((COALESCE(published_at, collected_at) AT TIME ZONE 'Asia/Seoul')::date)`,
  ),
  // 본문 기반 심층 분석 큐 상태: 대기 → 완료 / 제외 / 오류
  insightStatus: text("insight_status").notNull().default("대기"),
}, (table) => [
  uniqueIndex("news_articles_canonical_url_unique").on(table.canonicalUrl),
  index("news_articles_published_date_idx").on(table.publishedDateKst, table.publishedAt),
  index("news_articles_source_collected_idx").on(table.sourceId, table.collectedAt),
  index("news_articles_insight_queue_idx").on(table.insightStatus, table.publishedAt),
]);

export const newsInsights = pgTable("news_insights", {
  id: serial("id").primaryKey(),
  articleId: integer("article_id").notNull().references(() => newsArticles.id, { onDelete: "cascade" }),
  summary: text("summary").notNull().default(""),
  // 문자열 배열이다. text로 두면 (1) 검색이 JSON 구두점까지 훑어 배열 원소 경계를
  // 넘어 매칭되고 (2) 이중 인코딩이나 JSON 아닌 값이 조용히 저장된다. jsonb는 쓰기
  // 시점에 형식을 검증하고 원소 단위 질의를 인덱스로 받쳐 준다.
  keywords: jsonb("keywords").$type<string[]>().notNull().default([]),
  sectors: jsonb("sectors").$type<string[]>().notNull().default([]),
  evidence: jsonb("evidence").$type<string[]>().notNull().default([]),
  sentiment: text("sentiment").notNull().default("중립"),
  sentimentScore: integer("sentiment_score").notNull().default(50),
  materiality: text("materiality").notNull().default("낮음"),
  eventType: text("event_type").notNull().default("산업·시장동향"),
  impactHorizon: text("impact_horizon").notNull().default("당일"),
  marketView: text("market_view").notNull().default(""),
  bodyChars: integer("body_chars").notNull().default(0),
  engine: text("engine").notNull().default("규칙 기반"),
  model: text("model").notNull().default(""),
  attempts: integer("attempts").notNull().default(0),
  error: text("error"),
  createdAt: ts("created_at").notNull(),
  updatedAt: ts("updated_at").notNull(),
}, (table) => [
  uniqueIndex("news_insights_article_unique").on(table.articleId),
  // 키워드·업종 정확 일치 필터(`jsonb_exists`, `@>`)를 인덱스로 받는다.
  index("news_insights_keywords_gin").using("gin", table.keywords),
  index("news_insights_sectors_gin").using("gin", table.sectors),
]);

export const newsArticleSymbols = pgTable("news_article_symbols", {
  id: serial("id").primaryKey(),
  articleId: integer("article_id").notNull().references(() => newsArticles.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  company: text("company").notNull(),
  market: text("market").notNull().default("KR"),
  sector: text("sector").notNull().default(""),
  matchType: text("match_type").notNull().default("사전"),
  mentions: integer("mentions").notNull().default(1),
  relevance: integer("relevance").notNull().default(50),
  createdAt: ts("created_at").notNull(),
}, (table) => [
  uniqueIndex("news_article_symbols_unique").on(table.articleId, table.symbol),
  index("news_article_symbols_symbol_idx").on(table.symbol, table.createdAt),
]);

export const newsCrawlRuns = pgTable("news_crawl_runs", {
  id: serial("id").primaryKey(),
  sourceId: integer("source_id").notNull().references(() => newsSources.id, { onDelete: "cascade" }),
  status: text("status").notNull(),
  fetchedCount: integer("fetched_count").notNull().default(0),
  insertedCount: integer("inserted_count").notNull().default(0),
  error: text("error"),
  startedAt: ts("started_at").notNull(),
  completedAt: ts("completed_at"),
}, (table) => [index("news_crawl_runs_source_started_idx").on(table.sourceId, table.startedAt)]);

/**
 * 본문 분석에 쓸 LLM 공급자 목록. 우선순위가 낮은 숫자부터 시도하고, 한도 초과나
 * 인증 오류가 나면 cooldownUntil까지 건너뛰고 다음 공급자로 넘어간다. 무료 티어를
 * 여러 개 등록해 돌려 쓰는 것이 이 표의 목적이다.
 */
export const llmProviders = pgTable("llm_providers", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  baseUrl: text("base_url").notNull(),
  model: text("model").notNull(),
  apiKey: text("api_key").notNull().default(""),
  // 낮을수록 먼저 시도한다.
  priority: integer("priority").notNull().default(100),
  isActive: boolean("is_active").notNull().default(true),
  // 0이면 한도를 두지 않는다. 무료 티어의 일일 요청 수를 여기에 적는다.
  dailyLimit: integer("daily_limit").notNull().default(0),
  usedToday: integer("used_today").notNull().default(0),
  // 한국시간 기준으로 하루가 바뀌면 usedToday를 0으로 되돌린다.
  usageDateKst: date("usage_date_kst"),
  cooldownUntil: ts("cooldown_until"),
  lastStatus: text("last_status").notNull().default("대기"),
  lastError: text("last_error"),
  lastUsedAt: ts("last_used_at"),
  successCount: integer("success_count").notNull().default(0),
  failureCount: integer("failure_count").notNull().default(0),
  createdAt: ts("created_at").notNull(),
  updatedAt: ts("updated_at").notNull(),
}, (table) => [
  uniqueIndex("llm_providers_name_unique").on(table.name),
  index("llm_providers_order_idx").on(table.isActive, table.priority),
]);

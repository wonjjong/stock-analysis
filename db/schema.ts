import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const newsSources = sqliteTable("news_sources", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  name: text("name").notNull(),
  url: text("url").notNull(),
  resolvedUrl: text("resolved_url"),
  symbol: text("symbol").notNull(),
  company: text("company").notNull(),
  category: text("category").notNull().default("종합"),
  crawlHourKst: integer("crawl_hour_kst").notNull().default(6),
  isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),
  etag: text("etag"),
  lastModified: text("last_modified"),
  lastStatus: text("last_status").notNull().default("대기"),
  lastError: text("last_error"),
  lastCrawledAt: integer("last_crawled_at", { mode: "timestamp_ms" }),
  nextCrawlAt: integer("next_crawl_at", { mode: "timestamp_ms" }).notNull(),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
}, (table) => [
  uniqueIndex("news_sources_url_unique").on(table.url),
  index("news_sources_due_idx").on(table.isActive, table.nextCrawlAt),
]);

export const newsArticles = sqliteTable("news_articles", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sourceId: integer("source_id").notNull().references(() => newsSources.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  title: text("title").notNull(),
  canonicalUrl: text("canonical_url").notNull(),
  excerpt: text("excerpt").notNull().default(""),
  publishedAt: integer("published_at", { mode: "timestamp_ms" }),
  publishedDateKst: text("published_date_kst").notNull().default(""),
  contentHash: text("content_hash").notNull(),
  sentiment: text("sentiment").notNull(),
  sentimentScore: integer("sentiment_score").notNull(),
  materiality: text("materiality").notNull(),
  relevance: integer("relevance").notNull(),
  eventType: text("event_type").notNull(),
  scoreAdjustment: integer("score_adjustment").notNull(),
  analysisSummary: text("analysis_summary").notNull(),
  collectedAt: integer("collected_at", { mode: "timestamp_ms" }).notNull(),
}, (table) => [
  uniqueIndex("news_articles_canonical_url_unique").on(table.canonicalUrl),
  index("news_articles_published_date_idx").on(table.publishedDateKst, table.publishedAt),
  index("news_articles_source_collected_idx").on(table.sourceId, table.collectedAt),
]);

export const newsCrawlRuns = sqliteTable("news_crawl_runs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sourceId: integer("source_id").notNull().references(() => newsSources.id, { onDelete: "cascade" }),
  status: text("status").notNull(),
  fetchedCount: integer("fetched_count").notNull().default(0),
  insertedCount: integer("inserted_count").notNull().default(0),
  error: text("error"),
  startedAt: integer("started_at", { mode: "timestamp_ms" }).notNull(),
  completedAt: integer("completed_at", { mode: "timestamp_ms" }),
}, (table) => [index("news_crawl_runs_source_started_idx").on(table.sourceId, table.startedAt)]);

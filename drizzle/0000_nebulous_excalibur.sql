CREATE TABLE "news_article_symbols" (
	"id" serial PRIMARY KEY NOT NULL,
	"article_id" integer NOT NULL,
	"symbol" text NOT NULL,
	"company" text NOT NULL,
	"market" text DEFAULT 'KR' NOT NULL,
	"sector" text DEFAULT '' NOT NULL,
	"match_type" text DEFAULT '사전' NOT NULL,
	"mentions" integer DEFAULT 1 NOT NULL,
	"relevance" integer DEFAULT 50 NOT NULL,
	"created_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "news_articles" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"symbol" text NOT NULL,
	"title" text NOT NULL,
	"canonical_url" text NOT NULL,
	"excerpt" text DEFAULT '' NOT NULL,
	"published_at" timestamp with time zone,
	"content_hash" text NOT NULL,
	"sentiment" text NOT NULL,
	"sentiment_score" integer NOT NULL,
	"materiality" text NOT NULL,
	"relevance" integer NOT NULL,
	"event_type" text NOT NULL,
	"score_adjustment" integer NOT NULL,
	"analysis_summary" text NOT NULL,
	"collected_at" timestamp with time zone NOT NULL,
	"published_date_kst" date GENERATED ALWAYS AS (((COALESCE(published_at, collected_at) AT TIME ZONE 'Asia/Seoul')::date)) STORED,
	"insight_status" text DEFAULT '대기' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "news_crawl_runs" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"status" text NOT NULL,
	"fetched_count" integer DEFAULT 0 NOT NULL,
	"inserted_count" integer DEFAULT 0 NOT NULL,
	"error" text,
	"started_at" timestamp with time zone NOT NULL,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "news_insights" (
	"id" serial PRIMARY KEY NOT NULL,
	"article_id" integer NOT NULL,
	"summary" text DEFAULT '' NOT NULL,
	"keywords" text DEFAULT '[]' NOT NULL,
	"sectors" text DEFAULT '[]' NOT NULL,
	"evidence" text DEFAULT '[]' NOT NULL,
	"sentiment" text DEFAULT '중립' NOT NULL,
	"sentiment_score" integer DEFAULT 50 NOT NULL,
	"materiality" text DEFAULT '낮음' NOT NULL,
	"event_type" text DEFAULT '산업·시장동향' NOT NULL,
	"impact_horizon" text DEFAULT '당일' NOT NULL,
	"market_view" text DEFAULT '' NOT NULL,
	"body_chars" integer DEFAULT 0 NOT NULL,
	"engine" text DEFAULT '규칙 기반' NOT NULL,
	"model" text DEFAULT '' NOT NULL,
	"attempts" integer DEFAULT 0 NOT NULL,
	"error" text,
	"created_at" timestamp with time zone NOT NULL,
	"updated_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "news_sources" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"url" text NOT NULL,
	"resolved_url" text,
	"symbol" text NOT NULL,
	"company" text NOT NULL,
	"category" text DEFAULT '종합' NOT NULL,
	"crawl_hour_kst" integer DEFAULT 6 NOT NULL,
	"max_pages" integer DEFAULT 1 NOT NULL,
	"window_hours" integer DEFAULT 36 NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"etag" text,
	"last_modified" text,
	"last_status" text DEFAULT '대기' NOT NULL,
	"last_error" text,
	"last_crawled_at" timestamp with time zone,
	"next_crawl_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone NOT NULL,
	"updated_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
ALTER TABLE "news_article_symbols" ADD CONSTRAINT "news_article_symbols_article_id_news_articles_id_fk" FOREIGN KEY ("article_id") REFERENCES "public"."news_articles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "news_articles" ADD CONSTRAINT "news_articles_source_id_news_sources_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."news_sources"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "news_crawl_runs" ADD CONSTRAINT "news_crawl_runs_source_id_news_sources_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."news_sources"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "news_insights" ADD CONSTRAINT "news_insights_article_id_news_articles_id_fk" FOREIGN KEY ("article_id") REFERENCES "public"."news_articles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "news_article_symbols_unique" ON "news_article_symbols" USING btree ("article_id","symbol");--> statement-breakpoint
CREATE INDEX "news_article_symbols_symbol_idx" ON "news_article_symbols" USING btree ("symbol","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "news_articles_canonical_url_unique" ON "news_articles" USING btree ("canonical_url");--> statement-breakpoint
CREATE INDEX "news_articles_published_date_idx" ON "news_articles" USING btree ("published_date_kst","published_at");--> statement-breakpoint
CREATE INDEX "news_articles_source_collected_idx" ON "news_articles" USING btree ("source_id","collected_at");--> statement-breakpoint
CREATE INDEX "news_articles_insight_queue_idx" ON "news_articles" USING btree ("insight_status","published_at");--> statement-breakpoint
CREATE INDEX "news_crawl_runs_source_started_idx" ON "news_crawl_runs" USING btree ("source_id","started_at");--> statement-breakpoint
CREATE UNIQUE INDEX "news_insights_article_unique" ON "news_insights" USING btree ("article_id");--> statement-breakpoint
CREATE UNIQUE INDEX "news_sources_url_unique" ON "news_sources" USING btree ("url");--> statement-breakpoint
CREATE INDEX "news_sources_due_idx" ON "news_sources" USING btree ("is_active","next_crawl_at");
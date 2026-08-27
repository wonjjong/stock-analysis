CREATE TABLE `news_articles` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`source_id` integer NOT NULL,
	`symbol` text NOT NULL,
	`title` text NOT NULL,
	`canonical_url` text NOT NULL,
	`excerpt` text DEFAULT '' NOT NULL,
	`published_at` integer,
	`content_hash` text NOT NULL,
	`sentiment` text NOT NULL,
	`sentiment_score` integer NOT NULL,
	`materiality` text NOT NULL,
	`relevance` integer NOT NULL,
	`event_type` text NOT NULL,
	`score_adjustment` integer NOT NULL,
	`analysis_summary` text NOT NULL,
	`collected_at` integer NOT NULL,
	FOREIGN KEY (`source_id`) REFERENCES `news_sources`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `news_articles_canonical_url_unique` ON `news_articles` (`canonical_url`);--> statement-breakpoint
CREATE INDEX `news_articles_symbol_published_idx` ON `news_articles` (`symbol`,`published_at`);--> statement-breakpoint
CREATE INDEX `news_articles_source_collected_idx` ON `news_articles` (`source_id`,`collected_at`);--> statement-breakpoint
CREATE TABLE `news_crawl_runs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`source_id` integer NOT NULL,
	`status` text NOT NULL,
	`fetched_count` integer DEFAULT 0 NOT NULL,
	`inserted_count` integer DEFAULT 0 NOT NULL,
	`error` text,
	`started_at` integer NOT NULL,
	`completed_at` integer,
	FOREIGN KEY (`source_id`) REFERENCES `news_sources`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `news_crawl_runs_source_started_idx` ON `news_crawl_runs` (`source_id`,`started_at`);--> statement-breakpoint
CREATE TABLE `news_sources` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`url` text NOT NULL,
	`resolved_url` text,
	`symbol` text NOT NULL,
	`company` text NOT NULL,
	`crawl_hour_kst` integer DEFAULT 6 NOT NULL,
	`is_active` integer DEFAULT true NOT NULL,
	`etag` text,
	`last_modified` text,
	`last_status` text DEFAULT '대기' NOT NULL,
	`last_error` text,
	`last_crawled_at` integer,
	`next_crawl_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `news_sources_url_unique` ON `news_sources` (`url`);--> statement-breakpoint
CREATE INDEX `news_sources_due_idx` ON `news_sources` (`is_active`,`next_crawl_at`);
CREATE TABLE `news_article_symbols` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`article_id` integer NOT NULL,
	`symbol` text NOT NULL,
	`company` text NOT NULL,
	`market` text DEFAULT 'KR' NOT NULL,
	`sector` text DEFAULT '' NOT NULL,
	`match_type` text DEFAULT '사전' NOT NULL,
	`mentions` integer DEFAULT 1 NOT NULL,
	`relevance` integer DEFAULT 50 NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`article_id`) REFERENCES `news_articles`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `news_article_symbols_unique` ON `news_article_symbols` (`article_id`,`symbol`);--> statement-breakpoint
CREATE INDEX `news_article_symbols_symbol_idx` ON `news_article_symbols` (`symbol`,`created_at`);--> statement-breakpoint
CREATE TABLE `news_insights` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`article_id` integer NOT NULL,
	`summary` text DEFAULT '' NOT NULL,
	`keywords` text DEFAULT '[]' NOT NULL,
	`sectors` text DEFAULT '[]' NOT NULL,
	`evidence` text DEFAULT '[]' NOT NULL,
	`sentiment` text DEFAULT '중립' NOT NULL,
	`sentiment_score` integer DEFAULT 50 NOT NULL,
	`materiality` text DEFAULT '낮음' NOT NULL,
	`event_type` text DEFAULT '산업·시장동향' NOT NULL,
	`impact_horizon` text DEFAULT '당일' NOT NULL,
	`market_view` text DEFAULT '' NOT NULL,
	`body_chars` integer DEFAULT 0 NOT NULL,
	`engine` text DEFAULT '규칙 기반' NOT NULL,
	`model` text DEFAULT '' NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`error` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`article_id`) REFERENCES `news_articles`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `news_insights_article_unique` ON `news_insights` (`article_id`);--> statement-breakpoint
ALTER TABLE `news_articles` ADD `insight_status` text DEFAULT '대기' NOT NULL;--> statement-breakpoint
CREATE INDEX `news_articles_insight_queue_idx` ON `news_articles` (`insight_status`,`published_at`);
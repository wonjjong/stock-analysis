DROP INDEX `news_articles_symbol_published_idx`;--> statement-breakpoint
ALTER TABLE `news_articles` ADD `published_date_kst` text DEFAULT '' NOT NULL;--> statement-breakpoint
CREATE INDEX `news_articles_published_date_idx` ON `news_articles` (`published_date_kst`,`published_at`);--> statement-breakpoint
ALTER TABLE `news_sources` ADD `category` text DEFAULT '종합' NOT NULL;
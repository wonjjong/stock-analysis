-- drizzle-kit은 `SET DATA TYPE jsonb`만 생성하지만 Postgres는 두 가지를 더 요구한다.
--   1) text→jsonb에 명시적 USING ("cannot be cast automatically to type jsonb")
--   2) 기존 DEFAULT '[]'::text 를 먼저 떼기 ("default for column ... cannot be cast")
-- 기존 값은 앱이 JSON.stringify로 써 온 유효한 JSON 배열이라 `::jsonb`로 그대로
-- 옮겨진다. 유효하지 않은 값이 있으면 이 문장이 실패해 조용히 넘어가지 않는다.
ALTER TABLE "news_insights" ALTER COLUMN "keywords" DROP DEFAULT;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "keywords" SET DATA TYPE jsonb USING "keywords"::jsonb;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "keywords" SET DEFAULT '[]'::jsonb;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "sectors" DROP DEFAULT;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "sectors" SET DATA TYPE jsonb USING "sectors"::jsonb;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "sectors" SET DEFAULT '[]'::jsonb;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "evidence" DROP DEFAULT;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "evidence" SET DATA TYPE jsonb USING "evidence"::jsonb;--> statement-breakpoint
ALTER TABLE "news_insights" ALTER COLUMN "evidence" SET DEFAULT '[]'::jsonb;--> statement-breakpoint
CREATE INDEX "news_insights_keywords_gin" ON "news_insights" USING gin ("keywords");--> statement-breakpoint
CREATE INDEX "news_insights_sectors_gin" ON "news_insights" USING gin ("sectors");

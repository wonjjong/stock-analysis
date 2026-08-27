CREATE TABLE "llm_providers" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"base_url" text NOT NULL,
	"model" text NOT NULL,
	"api_key" text DEFAULT '' NOT NULL,
	"priority" integer DEFAULT 100 NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"daily_limit" integer DEFAULT 0 NOT NULL,
	"used_today" integer DEFAULT 0 NOT NULL,
	"usage_date_kst" date,
	"cooldown_until" timestamp with time zone,
	"last_status" text DEFAULT '대기' NOT NULL,
	"last_error" text,
	"last_used_at" timestamp with time zone,
	"success_count" integer DEFAULT 0 NOT NULL,
	"failure_count" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone NOT NULL,
	"updated_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX "llm_providers_name_unique" ON "llm_providers" USING btree ("name");--> statement-breakpoint
CREATE INDEX "llm_providers_order_idx" ON "llm_providers" USING btree ("is_active","priority");
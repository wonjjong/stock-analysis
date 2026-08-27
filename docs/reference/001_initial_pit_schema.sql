CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE instruments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), symbol text NOT NULL, market text NOT NULL,
  exchange text NOT NULL, name text NOT NULL, currency char(3) NOT NULL, sector text,
  active boolean NOT NULL DEFAULT true, UNIQUE(market, symbol)
);

CREATE TABLE price_bars (
  instrument_id uuid NOT NULL REFERENCES instruments(id), timeframe text NOT NULL,
  observed_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  open numeric NOT NULL, high numeric NOT NULL, low numeric NOT NULL, close numeric NOT NULL,
  volume numeric NOT NULL, provider text NOT NULL, raw_hash text,
  PRIMARY KEY(instrument_id, timeframe, observed_at, provider)
);
CREATE INDEX price_bars_pit ON price_bars(instrument_id, available_at DESC);

CREATE TABLE fundamental_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), instrument_id uuid NOT NULL REFERENCES instruments(id),
  fiscal_period text NOT NULL, period_end date NOT NULL, observed_at timestamptz NOT NULL,
  available_at timestamptz NOT NULL, revenue numeric, operating_income numeric, net_income numeric,
  eps numeric, book_value_per_share numeric, roe numeric, debt_ratio numeric, source text NOT NULL,
  revision integer NOT NULL DEFAULT 0, raw_payload jsonb NOT NULL DEFAULT '{}',
  UNIQUE(instrument_id, fiscal_period, revision, source)
);
CREATE INDEX fundamentals_pit ON fundamental_snapshots(instrument_id, available_at DESC);

CREATE TABLE valuation_snapshots (
  instrument_id uuid NOT NULL REFERENCES instruments(id), observed_at timestamptz NOT NULL,
  available_at timestamptz NOT NULL, price numeric NOT NULL, per numeric, forward_per numeric,
  pbr numeric, psr numeric, ev_ebitda numeric, dividend_yield numeric, sector_percentiles jsonb,
  PRIMARY KEY(instrument_id, observed_at)
);

CREATE TABLE macro_observations (
  series_key text NOT NULL, observed_at timestamptz NOT NULL, available_at timestamptz NOT NULL,
  value numeric NOT NULL, unit text NOT NULL, provider text NOT NULL,
  PRIMARY KEY(series_key, observed_at, provider)
);
CREATE INDEX macro_latest ON macro_observations(series_key, available_at DESC);

CREATE TABLE news_articles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), canonical_url text NOT NULL UNIQUE,
  publisher text NOT NULL, title text NOT NULL, author text, published_at timestamptz,
  first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
  language text, status text NOT NULL DEFAULT 'active', robots_allowed boolean NOT NULL DEFAULT true,
  content_hash text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE news_content_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), article_id uuid NOT NULL REFERENCES news_articles(id),
  fetched_at timestamptz NOT NULL, available_at timestamptz NOT NULL, extractor_version text NOT NULL,
  cleaned_text text NOT NULL, raw_object_key text, content_hash text NOT NULL,
  UNIQUE(article_id, content_hash)
);

CREATE TABLE news_clusters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), representative_article_id uuid REFERENCES news_articles(id),
  event_key text NOT NULL, created_at timestamptz NOT NULL, summary text
);

CREATE TABLE article_stock_links (
  article_id uuid NOT NULL REFERENCES news_articles(id), instrument_id uuid NOT NULL REFERENCES instruments(id),
  relevance numeric NOT NULL CHECK(relevance BETWEEN 0 AND 1), sentiment numeric CHECK(sentiment BETWEEN -1 AND 1),
  materiality text NOT NULL, model_version text NOT NULL, evidence_spans jsonb NOT NULL DEFAULT '[]',
  PRIMARY KEY(article_id, instrument_id, model_version)
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), auth_subject text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE watchlist_items (
  user_id uuid NOT NULL REFERENCES users(id), instrument_id uuid NOT NULL REFERENCES instruments(id),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id, instrument_id)
);
CREATE TABLE positions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id),
  instrument_id uuid NOT NULL REFERENCES instruments(id), quantity numeric NOT NULL CHECK(quantity > 0),
  average_price numeric NOT NULL CHECK(average_price >= 0), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id, instrument_id)
);

CREATE TABLE recommendation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), market text NOT NULL, as_of timestamptz NOT NULL,
  universe_version text NOT NULL, feature_version text NOT NULL, model_version text NOT NULL,
  macro_snapshot jsonb NOT NULL, status text NOT NULL, metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(market, as_of, model_version)
);
CREATE TABLE recommendations (
  run_id uuid NOT NULL REFERENCES recommendation_runs(id), instrument_id uuid NOT NULL REFERENCES instruments(id),
  rank integer NOT NULL, score numeric NOT NULL, confidence numeric NOT NULL, action text NOT NULL,
  entry_low numeric NOT NULL, entry_high numeric NOT NULL, target_price numeric NOT NULL, stop_price numeric NOT NULL,
  factor_scores jsonb NOT NULL, reasons jsonb NOT NULL, PRIMARY KEY(run_id, instrument_id), UNIQUE(run_id, rank)
);

CREATE TABLE analysis_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid REFERENCES users(id),
  instrument_id uuid NOT NULL REFERENCES instruments(id), requested_at timestamptz NOT NULL DEFAULT now(),
  data_cutoff_at timestamptz NOT NULL, status text NOT NULL, refresh boolean NOT NULL DEFAULT false,
  error_code text, idempotency_key text NOT NULL UNIQUE
);
CREATE TABLE analyses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), job_id uuid NOT NULL UNIQUE REFERENCES analysis_jobs(id),
  instrument_id uuid NOT NULL REFERENCES instruments(id), version integer NOT NULL,
  stance text NOT NULL, confidence integer NOT NULL, report jsonb NOT NULL,
  entry_low numeric NOT NULL, entry_high numeric NOT NULL, target_price numeric NOT NULL, stop_price numeric NOT NULL,
  prompt_version text NOT NULL, model text NOT NULL, generated_at timestamptz NOT NULL,
  superseded_by uuid REFERENCES analyses(id), UNIQUE(instrument_id, version)
);
CREATE TABLE analysis_evidence (
  analysis_id uuid NOT NULL REFERENCES analyses(id), evidence_type text NOT NULL,
  evidence_id uuid NOT NULL, claim_key text NOT NULL, quoted_span text,
  PRIMARY KEY(analysis_id, evidence_type, evidence_id, claim_key)
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
-- Supabase 배포 시 auth.uid()와 auth_subject를 연결한 사용자별 정책을 추가한다.

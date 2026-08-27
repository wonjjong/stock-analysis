import type { SqlDatabase } from "../../db/sql";
import { fetchArticleBody } from "./article-body";
import { extractKeywords } from "./keywords";
import { availableProviders, llmJsonWithFailover, type ProviderAttempt } from "./llm";
import { analyzeNewsLocally } from "./news-analysis";
import { matchSymbols, type SymbolMatch } from "./symbol-dictionary";

const MAX_ATTEMPTS = 3;
const LLM_BODY_LIMIT = 6_000;
const HORIZONS = ["당일", "단기(1~4주)", "중기(1~2분기)", "장기(1년+)"];
const SENTIMENTS = ["긍정", "부정", "중립"];
const MATERIALITIES = ["높음", "보통", "낮음"];

// 파이프라인은 정수 밀리초로 동작한다. 컬럼은 timestamptz이므로 SQL 경계에서만 Date로 바꾼다.
const at = (ms: number | null | undefined) => (ms == null ? null : new Date(ms));

type QueueRow = { id: number; title: string; canonical_url: string; excerpt: string; insight_status: string };

export type Insight = {
  summary: string; keywords: string[]; sectors: string[]; evidence: string[];
  sentiment: string; sentimentScore: number; materiality: string; eventType: string;
  impactHorizon: string; marketView: string; scoreAdjustment: number;
  engine: string; model: string;
};

export type ProcessSummary = { picked: number; done: number; llm: number; rule: number; failed: number; providers: Record<string, number> };

const system = [
  "당신은 기관투자자를 위한 뉴스 애널리스트다.",
  "기사에 명시된 사실만 사용하고 없는 수치를 만들어내지 않는다.",
  "한국어로 답하고 반드시 지정한 JSON 객체 하나만 출력한다.",
  "필드: summary(3문장 이내 요약), keywords(핵심 키워드 3~8개), sectors(영향 업종 0~4개),",
  "evidence(기사에서 인용한 근거 문장 1~3개), sentiment(긍정|부정|중립), sentimentScore(0~100),",
  "materiality(높음|보통|낮음), eventType(짧은 사건 유형), impactHorizon(당일|단기(1~4주)|중기(1~2분기)|장기(1년+)),",
  "marketView(시황·업종 관점 한두 문장), scoreAdjustment(-8~8 정수), symbols(기사가 직접 다루는 상장사명 0~5개).",
].join(" ");

function clamp(value: unknown, min: number, max: number, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(min, Math.min(max, Math.round(number))) : fallback;
}

function stringList(value: unknown, limit: number, maxLength = 60) {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string")
    .map((item) => item.trim().slice(0, maxLength)).filter(Boolean).slice(0, limit);
}

function pick(value: unknown, allowed: string[], fallback: string) {
  return typeof value === "string" && allowed.includes(value) ? value : fallback;
}

export function ruleInsight(title: string, body: string): Insight {
  const text = `${title}. ${body}`.slice(0, 8_000);
  const base = analyzeNewsLocally(text, "MARKET", "시장 전체");
  const symbols = matchSymbols(title, body);
  const sectors = [...new Set(symbols.map((item) => item.sector))].slice(0, 4);
  const lead = body.split(/\n+/).map((line) => line.trim()).filter((line) => line.length > 30).slice(0, 2);
  return {
    summary: (lead.join(" ") || body || title).slice(0, 400),
    keywords: extractKeywords(title, body),
    sectors,
    evidence: base.keyEvidence,
    sentiment: base.sentiment,
    sentimentScore: Math.round(base.sentimentScore),
    materiality: base.materiality,
    eventType: base.eventType,
    impactHorizon: base.impactHorizon,
    marketView: sectors.length ? `${sectors.join(", ")} 업종에 관련된 보도입니다.` : "특정 업종을 지목하기 어려운 일반 보도입니다.",
    scoreAdjustment: base.scoreAdjustment,
    engine: "규칙 기반",
    model: "",
  };
}

function llmInsight(parsed: Record<string, unknown>, base: Insight, engine: string, model: string) {
  const keywords = stringList(parsed.keywords, 8, 30);
  const evidence = stringList(parsed.evidence, 3, 200);
  const insight: Insight = {
    summary: (typeof parsed.summary === "string" ? parsed.summary : base.summary).trim().slice(0, 800),
    keywords: keywords.length ? keywords : base.keywords,
    sectors: stringList(parsed.sectors, 4, 30),
    evidence: evidence.length ? evidence : base.evidence,
    sentiment: pick(parsed.sentiment, SENTIMENTS, base.sentiment),
    sentimentScore: clamp(parsed.sentimentScore, 0, 100, base.sentimentScore),
    materiality: pick(parsed.materiality, MATERIALITIES, base.materiality),
    eventType: typeof parsed.eventType === "string" && parsed.eventType.trim() ? parsed.eventType.trim().slice(0, 40) : base.eventType,
    impactHorizon: pick(parsed.impactHorizon, HORIZONS, base.impactHorizon),
    marketView: (typeof parsed.marketView === "string" ? parsed.marketView : base.marketView).trim().slice(0, 400),
    scoreAdjustment: clamp(parsed.scoreAdjustment, -8, 8, base.scoreAdjustment),
    engine,
    model,
  };
  if (!insight.sectors.length) insight.sectors = base.sectors;
  return insight;
}

/** 규칙 단계에서 종목이 잡혔거나 중요한 기사만 LLM으로 보낸다. 무료 한도를 아끼기 위한 필터다. */
function deservesLlm(base: Insight, symbols: SymbolMatch[], bodyChars: number) {
  if (symbols.length) return true;
  if (base.materiality !== "낮음") return true;
  return bodyChars >= 1_200;
}

async function processArticle(db: SqlDatabase, row: QueueRow, useLlm: boolean, now: number) {
  let body = row.excerpt ?? "";
  try {
    const fetched = await fetchArticleBody(row.canonical_url);
    if (fetched.chars > body.length) body = fetched.text;
  } catch {
    // 본문 페이지를 못 읽으면 수집 당시의 요약으로 분석을 이어간다.
  }

  const base = ruleInsight(row.title, body);
  const symbols = matchSymbols(row.title, body);
  let insight = base;
  let llmUsed = false;
  let attempts: ProviderAttempt[] = [];

  if (useLlm && deservesLlm(base, symbols, body.length)) {
    const user = JSON.stringify({ title: row.title, article: body.slice(0, LLM_BODY_LIMIT) });
    const chain = await llmJsonWithFailover(db, system, user, now);
    attempts = chain.attempts;
    if (chain.parsed && chain.provider) {
      insight = llmInsight(chain.parsed as Record<string, unknown>, base, chain.provider.name, chain.provider.model);
      llmUsed = true;
    }
    // 모든 공급자가 실패하면 규칙 기반 결과를 그대로 쓴다. 기사는 완료로 남는다.
  }

  const statements = [
    db.prepare(`INSERT INTO news_insights
      (article_id, summary, keywords, sectors, evidence, sentiment, sentiment_score, materiality, event_type, impact_horizon, market_view, body_chars, engine, model, attempts, error, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
      ON CONFLICT (article_id) DO UPDATE SET summary = excluded.summary, keywords = excluded.keywords, sectors = excluded.sectors,
        evidence = excluded.evidence, sentiment = excluded.sentiment, sentiment_score = excluded.sentiment_score,
        materiality = excluded.materiality, event_type = excluded.event_type, impact_horizon = excluded.impact_horizon,
        market_view = excluded.market_view, body_chars = excluded.body_chars, engine = excluded.engine, model = excluded.model,
        attempts = news_insights.attempts + 1, error = NULL, updated_at = excluded.updated_at`)
      // jsonb는 읽기와 쓰기가 비대칭이다. 드라이버는 조회 결과를 이미 파싱된 배열로
      // 주지만, 파라미터로 받은 JS 배열은 Postgres 배열 리터럴(`{a,b}`)로 직렬화해
      // jsonb 파싱이 실패한다("invalid input syntax for type json"). 그래서 쓰기에는
      // JSON 문자열을 넘긴다. (객체는 JSON으로 직렬화되지만 배열은 그렇지 않다.)
      .bind(row.id, insight.summary, JSON.stringify(insight.keywords), JSON.stringify(insight.sectors), JSON.stringify(insight.evidence),
        insight.sentiment, insight.sentimentScore, insight.materiality, insight.eventType, insight.impactHorizon,
        insight.marketView, body.length, insight.engine, insight.model, at(now), at(now)),
    db.prepare("DELETE FROM news_article_symbols WHERE article_id = ?").bind(row.id),
    db.prepare(`UPDATE news_articles SET insight_status = '완료', sentiment = ?, sentiment_score = ?, materiality = ?,
        event_type = ?, score_adjustment = ?, analysis_summary = ?, relevance = ?, symbol = ? WHERE id = ?`)
      .bind(insight.sentiment, insight.sentimentScore, insight.materiality, insight.eventType, insight.scoreAdjustment,
        insight.summary.slice(0, 500), symbols[0]?.relevance ?? 40, symbols[0]?.symbol ?? "GENERAL", row.id),
  ];
  for (const symbol of symbols) {
    statements.push(db.prepare(`INSERT INTO news_article_symbols
      (article_id, symbol, company, market, sector, match_type, mentions, relevance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (article_id, symbol) DO UPDATE SET company = excluded.company, market = excluded.market,
        sector = excluded.sector, match_type = excluded.match_type, mentions = excluded.mentions,
        relevance = excluded.relevance, created_at = excluded.created_at`)
      .bind(row.id, symbol.symbol, symbol.company, symbol.market, symbol.sector, symbol.matchType, symbol.mentions, symbol.relevance, at(now)));
  }
  await db.batch(statements);
  return { llmUsed, attempts };
}

async function markFailure(db: SqlDatabase, row: QueueRow, message: string, now: number) {
  const current = await db.prepare("SELECT attempts FROM news_insights WHERE article_id = ?").bind(row.id).first<{ attempts: number }>();
  const attempts = (current?.attempts ?? 0) + 1;
  await db.batch([
    db.prepare(`INSERT INTO news_insights (article_id, attempts, error, created_at, updated_at) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT (article_id) DO UPDATE SET attempts = ?, error = excluded.error, updated_at = excluded.updated_at`)
      .bind(row.id, attempts, message, at(now), at(now), attempts),
    db.prepare("UPDATE news_articles SET insight_status = ? WHERE id = ?")
      .bind(attempts >= MAX_ATTEMPTS ? "오류" : "대기", row.id),
  ]);
}

/** 대기 중인 기사를 정해진 개수만큼 본문 분석한다. cron과 수동 실행이 같은 함수를 쓴다. */
export async function processPendingInsights(db: SqlDatabase, limit = 12, now = Date.now()): Promise<ProcessSummary> {
  const size = Math.max(1, Math.min(50, Math.trunc(limit)));
  const queue = await db.prepare(`SELECT a.id, a.title, a.canonical_url, a.excerpt, a.insight_status
    FROM news_articles a WHERE a.insight_status = '대기'
    ORDER BY COALESCE(a.published_at, a.collected_at) DESC LIMIT ?`).bind(size).all<QueueRow>();

  // 공급자가 하나도 없으면 매 기사마다 조회하지 않고 규칙 기반으로만 돈다.
  const useLlm = (await availableProviders(db, now)).length > 0;
  const result: ProcessSummary = { picked: queue.results.length, done: 0, llm: 0, rule: 0, failed: 0, providers: {} };
  for (const row of queue.results) {
    try {
      const { llmUsed, attempts } = await processArticle(db, row, useLlm, now);
      for (const attempt of attempts) {
        const key = `${attempt.name} · ${attempt.kind}`;
        result.providers[key] = (result.providers[key] ?? 0) + 1;
      }
      result.done += 1;
      if (llmUsed) result.llm += 1; else result.rule += 1;
    } catch (reason) {
      result.failed += 1;
      await markFailure(db, row, reason instanceof Error ? reason.message.slice(0, 300) : "본문 분석에 실패했습니다.", now);
    }
  }
  return result;
}

export async function insightQueueStats(db: SqlDatabase) {
  const rows = await db.prepare("SELECT insight_status AS status, COUNT(*) AS count FROM news_articles GROUP BY insight_status").all<{ status: string; count: number }>();
  const counts = Object.fromEntries(rows.results.map((row: { status: string; count: number }) => [row.status, row.count]));
  const engines = await db.prepare("SELECT engine, COUNT(*) AS count FROM news_insights GROUP BY engine").all<{ engine: string; count: number }>();
  const ready = await availableProviders(db);
  return {
    pending: counts["대기"] ?? 0,
    done: counts["완료"] ?? 0,
    failed: counts["오류"] ?? 0,
    engines: Object.fromEntries(engines.results.map((row: { engine: string; count: number }) => [row.engine, row.count])),
    providers: ready.map((row) => ({ id: row.id, name: row.name, model: row.model, priority: row.priority })),
    llmConfigured: ready.length > 0,
  };
}

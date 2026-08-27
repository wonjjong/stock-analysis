import type { SqlDatabase } from "../../db/sql";

/**
 * OpenAI 호환 Chat Completions 어댑터.
 * base URL과 모델명만 바꾸면 OpenAI, Gemini(호환 엔드포인트), DeepSeek, Qwen,
 * Groq, OpenRouter를 같은 코드로 호출합니다.
 */
export type LlmConfig = { baseUrl: string; apiKey: string; model: string; timeoutMs: number };

const DEFAULT_TIMEOUT_MS = 25_000;

function timeoutMs() {
  return Math.max(5_000, Math.min(60_000, Number(process.env.SIGNALIST_LLM_TIMEOUT_MS) || DEFAULT_TIMEOUT_MS));
}

/** DB에 공급자가 하나도 없을 때만 쓰는 환경변수 폴백. */
export function llmConfig(): LlmConfig | null {
  const apiKey = process.env.SIGNALIST_LLM_API_KEY ?? process.env.SIGNALIST_OPENAI_API_KEY;
  if (!apiKey) return null;
  const baseUrl = (process.env.SIGNALIST_LLM_BASE_URL ?? "https://api.openai.com/v1").replace(/\/+$/, "");
  const model = process.env.SIGNALIST_LLM_MODEL ?? process.env.SIGNALIST_OPENAI_NEWS_MODEL ?? "gpt-5.6-terra";
  return { baseUrl, apiKey, model, timeoutMs: timeoutMs() };
}

function extractJson(text: string) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const body = (fenced?.[1] ?? text).trim();
  const start = body.indexOf("{");
  const end = body.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("모델이 JSON을 반환하지 않았습니다.");
  return JSON.parse(body.slice(start, end + 1)) as unknown;
}

export class LlmError extends Error {
  constructor(message: string, readonly kind: FailureKind, readonly status = 0) {
    super(message);
    this.name = "LlmError";
  }
}

export type FailureKind = "한도 초과" | "인증 오류" | "일시 오류" | "요청 오류";

/**
 * 실패를 종류별로 나눈다. 한도 초과와 인증 오류는 같은 키로 다시 시도해도 소용이
 * 없으므로 길게 쉬게 하고, 일시 오류만 짧게 쉬었다가 다시 쓴다.
 */
export function classifyFailure(status: number, detail: string): FailureKind {
  if (status === 429) return "한도 초과";
  if (status === 401 || status === 403) return "인증 오류";
  if (status === 402) return "한도 초과";
  if (status >= 500 || status === 408 || status === 0) return "일시 오류";
  if (status === 400 && /quota|exhaust|limit|billing|credit/i.test(detail)) return "한도 초과";
  return "요청 오류";
}

export async function llmJson(config: LlmConfig, system: string, user: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${config.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${config.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: config.model,
        messages: [{ role: "system", content: system }, { role: "user", content: user }],
        response_format: { type: "json_object" },
        temperature: 0.2,
      }),
      signal: AbortSignal.timeout(config.timeoutMs),
    });
  } catch (reason) {
    const message = reason instanceof Error && reason.name === "TimeoutError"
      ? `응답이 ${Math.round(config.timeoutMs / 1000)}초를 넘겨 끊었습니다.`
      : reason instanceof Error ? reason.message : "네트워크 오류";
    throw new LlmError(message, "일시 오류");
  }
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new LlmError(`${response.status} ${detail}`, classifyFailure(response.status, detail), response.status);
  }
  const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
  const content = payload.choices?.[0]?.message?.content;
  if (!content) throw new LlmError("응답에 본문이 없습니다.", "요청 오류", response.status);
  try {
    return extractJson(content);
  } catch (reason) {
    throw new LlmError(reason instanceof Error ? reason.message : "JSON 해석 실패", "요청 오류", response.status);
  }
}

export type ProviderRow = {
  id: number; name: string; base_url: string; model: string; api_key: string;
  priority: number; is_active: boolean; daily_limit: number; used_today: number;
  usage_date_kst: string | null; cooldown_until: number | null;
  last_status: string; last_error: string | null; last_used_at: number | null;
  success_count: number; failure_count: number;
};

export type ProviderAttempt = { name: string; kind: FailureKind | "성공"; detail?: string };

export function dateKst(time = Date.now()) {
  return new Date(time + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/** 실패 종류별로 얼마나 쉬게 할지. */
export function cooldownUntil(kind: FailureKind, now: number) {
  if (kind === "한도 초과") {
    // 분당 한도인지 일일 한도인지 응답만 보고는 알 수 없다. 한 시간 쉬되 한국시간
    // 자정을 넘기지 않는다. 자정이면 어차피 무료 티어 사용량이 초기화된다.
    const kst = new Date(now + 9 * 60 * 60 * 1000);
    const midnight = Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate() + 1) - 9 * 60 * 60 * 1000;
    return Math.min(midnight, now + 60 * 60 * 1000);
  }
  if (kind === "인증 오류") return now + 6 * 60 * 60 * 1000;
  if (kind === "요청 오류") return now + 30 * 60 * 1000;
  return now + 5 * 60 * 1000;
}

/** 지금 쓸 수 있는 공급자만 우선순위 순으로 가져온다. */
export async function availableProviders(db: SqlDatabase, now = Date.now()): Promise<ProviderRow[]> {
  const rows = await db.prepare(`SELECT id, name, base_url, model, api_key, priority, is_active, daily_limit,
      used_today, usage_date_kst, cooldown_until, last_status, last_error, last_used_at, success_count, failure_count
      FROM llm_providers WHERE is_active = true AND api_key <> ''
      ORDER BY priority, id`).all<ProviderRow>();
  const today = dateKst(now);
  // DB에 공급자가 하나도 없을 때만 환경변수 설정을 마지막 수단으로 끼워 넣는다.
  if (!rows.results.length) {
    const fallback = llmConfig();
    if (!fallback) return [];
    return [{
      id: 0, name: "환경변수", base_url: fallback.baseUrl, model: fallback.model, api_key: fallback.apiKey,
      priority: 999, is_active: true, daily_limit: 0, used_today: 0, usage_date_kst: null, cooldown_until: null,
      last_status: "대기", last_error: null, last_used_at: null, success_count: 0, failure_count: 0,
    }];
  }
  return rows.results.filter((row) => {
    if (row.cooldown_until && row.cooldown_until > now) return false;
    if (!row.daily_limit) return true;
    // 날짜가 바뀌었으면 사용량은 0부터 다시 센다.
    if (row.usage_date_kst !== today) return true;
    return row.used_today < row.daily_limit;
  });
}

async function recordSuccess(db: SqlDatabase, provider: ProviderRow, now: number) {
  if (!provider.id) return;
  const today = dateKst(now);
  await db.prepare(`UPDATE llm_providers SET
      used_today = CASE WHEN usage_date_kst = ? THEN used_today + 1 ELSE 1 END,
      usage_date_kst = ?, cooldown_until = NULL, last_status = '정상', last_error = NULL,
      last_used_at = ?, success_count = success_count + 1, updated_at = ?
    WHERE id = ?`).bind(today, today, new Date(now), new Date(now), provider.id).run();
}

async function recordFailure(db: SqlDatabase, provider: ProviderRow, kind: FailureKind, message: string, now: number) {
  if (!provider.id) return;
  const today = dateKst(now);
  const until = cooldownUntil(kind, now);
  await db.prepare(`UPDATE llm_providers SET
      used_today = CASE WHEN usage_date_kst = ? THEN used_today + 1 ELSE 1 END,
      usage_date_kst = ?, cooldown_until = ?, last_status = ?, last_error = ?,
      last_used_at = ?, failure_count = failure_count + 1, updated_at = ?
    WHERE id = ?`)
    .bind(today, today, new Date(until), kind, message.slice(0, 400), new Date(now), new Date(now), provider.id).run();
}

export type ChainResult = { parsed: unknown | null; provider: ProviderRow | null; attempts: ProviderAttempt[] };

/**
 * 우선순위가 높은 공급자부터 호출하고, 한도 초과·인증 오류·일시 오류가 나면
 * 해당 공급자를 쉬게 한 뒤 다음 공급자로 넘어간다. 전부 실패하면 null이다.
 */
export async function llmJsonWithFailover(db: SqlDatabase, system: string, user: string, now = Date.now()): Promise<ChainResult> {
  const providers = await availableProviders(db, now);
  const attempts: ProviderAttempt[] = [];
  for (const provider of providers) {
    const config: LlmConfig = { baseUrl: provider.base_url.replace(/\/+$/, ""), apiKey: provider.api_key, model: provider.model, timeoutMs: timeoutMs() };
    try {
      const parsed = await llmJson(config, system, user);
      await recordSuccess(db, provider, now);
      attempts.push({ name: provider.name, kind: "성공" });
      return { parsed, provider, attempts };
    } catch (reason) {
      const kind = reason instanceof LlmError ? reason.kind : "일시 오류";
      const message = reason instanceof Error ? reason.message : "알 수 없는 오류";
      await recordFailure(db, provider, kind, message, now);
      attempts.push({ name: provider.name, kind, detail: message.slice(0, 160) });
    }
  }
  return { parsed: null, provider: null, attempts };
}

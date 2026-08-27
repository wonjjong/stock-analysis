import { getD1 } from "../../../../db";
import { llmPresets } from "../../../lib/llm-presets";

type CreateBody = { name?: string; baseUrl?: string; model?: string; apiKey?: string; priority?: number; dailyLimit?: number };

/** 키가 평문으로 나가므로 https만 허용한다. 로컬 목 서버만 예외로 둔다. */
export function isAllowedBaseUrl(value: string) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return true;
    return url.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  } catch { return false; }
}

/** 키는 절대 그대로 돌려주지 않는다. 등록 여부와 끝 네 글자만 보여준다. */
function maskKey(value: string) {
  if (!value) return "";
  return value.length <= 8 ? "••••" : `••••${value.slice(-4)}`;
}

export async function GET() {
  const db = getD1();
  const rows = await db.prepare(`SELECT id, name, base_url, model, api_key, priority, is_active, daily_limit,
      used_today, usage_date_kst, cooldown_until, last_status, last_error, last_used_at, success_count, failure_count
      FROM llm_providers ORDER BY priority, id`).all<Record<string, unknown>>();
  return Response.json({
    providers: rows.results.map((row) => ({ ...row, api_key: maskKey(String(row.api_key ?? "")), has_key: Boolean(row.api_key) })),
    presets: llmPresets,
  });
}

export async function POST(request: Request) {
  const body = await request.json() as CreateBody;
  const name = body.name?.trim().slice(0, 60) ?? "";
  const baseUrl = body.baseUrl?.trim().replace(/\/+$/, "").slice(0, 300) ?? "";
  const model = body.model?.trim().slice(0, 120) ?? "";
  const apiKey = body.apiKey?.trim().slice(0, 400) ?? "";
  if (!name || !baseUrl || !model) return Response.json({ error: "이름, base URL, 모델명이 필요합니다." }, { status: 400 });
  if (!isAllowedBaseUrl(baseUrl)) return Response.json({ error: "base URL은 https여야 합니다. (로컬 테스트용 localhost만 예외)" }, { status: 400 });

  const priority = Math.max(1, Math.min(999, Math.trunc(Number(body.priority)) || 100));
  const dailyLimit = Math.max(0, Math.min(1_000_000, Math.trunc(Number(body.dailyLimit)) || 0));
  const now = new Date();
  try {
    const created = await getD1().prepare(`INSERT INTO llm_providers
      (name, base_url, model, api_key, priority, daily_limit, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id`)
      .bind(name, baseUrl, model, apiKey, priority, dailyLimit, now, now).first<{ id: number }>();
    return Response.json({ id: created?.id }, { status: 201 });
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : "공급자를 저장하지 못했습니다.";
    if (/unique|duplicate/i.test(message)) return Response.json({ error: "같은 이름의 공급자가 이미 있습니다." }, { status: 409 });
    return Response.json({ error: message }, { status: 500 });
  }
}

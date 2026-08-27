import { getD1 } from "../../../../../db";
import { isAllowedBaseUrl } from "../route";

type PatchBody = { isActive?: boolean; priority?: number; model?: string; apiKey?: string; dailyLimit?: number; baseUrl?: string; clearCooldown?: boolean };

function providerId(params: { id: string }) {
  const id = Number(params.id);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const id = providerId(await context.params);
  if (!id) return Response.json({ error: "잘못된 공급자입니다." }, { status: 400 });
  const body = await request.json() as PatchBody;

  const sets: string[] = [];
  const values: unknown[] = [];
  if (typeof body.isActive === "boolean") { sets.push("is_active = ?"); values.push(body.isActive); }
  if (Number.isFinite(body.priority)) { sets.push("priority = ?"); values.push(Math.max(1, Math.min(999, Math.trunc(body.priority!)))); }
  if (Number.isFinite(body.dailyLimit)) { sets.push("daily_limit = ?"); values.push(Math.max(0, Math.min(1_000_000, Math.trunc(body.dailyLimit!)))); }
  if (typeof body.model === "string" && body.model.trim()) { sets.push("model = ?"); values.push(body.model.trim().slice(0, 120)); }
  if (typeof body.baseUrl === "string" && isAllowedBaseUrl(body.baseUrl.trim())) { sets.push("base_url = ?"); values.push(body.baseUrl.trim().replace(/\/+$/, "").slice(0, 300)); }
  // 빈 문자열이면 키를 지우지 않고 그대로 둔다. 화면이 마스킹된 값을 되돌려 보내기 때문이다.
  if (typeof body.apiKey === "string" && body.apiKey.trim()) { sets.push("api_key = ?"); values.push(body.apiKey.trim().slice(0, 400)); }
  if (body.clearCooldown) { sets.push("cooldown_until = NULL", "last_status = '대기'", "last_error = NULL"); }
  if (!sets.length) return Response.json({ error: "바꿀 값이 없습니다." }, { status: 400 });

  sets.push("updated_at = ?");
  values.push(new Date(), id);
  const result = await getD1().prepare(`UPDATE llm_providers SET ${sets.join(", ")} WHERE id = ?`).bind(...values).run();
  if (!result.meta.changes) return Response.json({ error: "공급자를 찾지 못했습니다." }, { status: 404 });
  return Response.json({ ok: true });
}

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const id = providerId(await context.params);
  if (!id) return Response.json({ error: "잘못된 공급자입니다." }, { status: 400 });
  const result = await getD1().prepare("DELETE FROM llm_providers WHERE id = ?").bind(id).run();
  if (!result.meta.changes) return Response.json({ error: "공급자를 찾지 못했습니다." }, { status: 404 });
  return Response.json({ ok: true });
}

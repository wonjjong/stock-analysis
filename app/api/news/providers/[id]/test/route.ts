import { getD1 } from "../../../../../../db";
import { llmJson, LlmError, type LlmConfig } from "../../../../../lib/llm";

/** 등록한 키가 실제로 도는지 확인한다. 아주 짧은 요청이라 무료 한도를 거의 쓰지 않는다. */
export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  const id = Number((await context.params).id);
  if (!Number.isInteger(id) || id <= 0) return Response.json({ error: "잘못된 공급자입니다." }, { status: 400 });

  const db = getD1();
  const provider = await db.prepare("SELECT id, name, base_url, model, api_key FROM llm_providers WHERE id = ?")
    .bind(id).first<{ id: number; name: string; base_url: string; model: string; api_key: string }>();
  if (!provider) return Response.json({ error: "공급자를 찾지 못했습니다." }, { status: 404 });
  if (!provider.api_key) return Response.json({ error: "API 키가 비어 있습니다." }, { status: 400 });

  const config: LlmConfig = { baseUrl: provider.base_url.replace(/\/+$/, ""), apiKey: provider.api_key, model: provider.model, timeoutMs: 20_000 };
  const now = new Date();
  try {
    await llmJson(config, '반드시 {"ok": true} 형태의 JSON 객체만 출력한다.', '{"ping":1}');
    await db.prepare("UPDATE llm_providers SET last_status = '정상', last_error = NULL, cooldown_until = NULL, updated_at = ? WHERE id = ?").bind(now, id).run();
    return Response.json({ ok: true, name: provider.name, model: provider.model });
  } catch (reason) {
    const kind = reason instanceof LlmError ? reason.kind : "일시 오류";
    const message = reason instanceof Error ? reason.message.slice(0, 300) : "호출에 실패했습니다.";
    await db.prepare("UPDATE llm_providers SET last_status = ?, last_error = ?, updated_at = ? WHERE id = ?").bind(kind, message, now, id).run();
    return Response.json({ ok: false, kind, error: message }, { status: 200 });
  }
}

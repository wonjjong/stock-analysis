import { getD1 } from "../../../../../db";
import { nextRunAt } from "../../../../lib/news-crawler";

type Context = { params: Promise<{ id: string }> };

function sourceId(value: string) {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function PATCH(request: Request, { params }: Context) {
  const id = sourceId((await params).id);
  if (!id) return Response.json({ error: "잘못된 소스 ID입니다." }, { status: 400 });
  const body = await request.json() as { isActive?: boolean; crawlHourKst?: number };
  const db = getD1();
  const current = await db.prepare("SELECT crawl_hour_kst, is_active FROM news_sources WHERE id = ?").bind(id).first<{ crawl_hour_kst: number; is_active: number }>();
  if (!current) return Response.json({ error: "뉴스 소스를 찾지 못했습니다." }, { status: 404 });
  const active = body.isActive === undefined ? Boolean(current.is_active) : body.isActive;
  const hour = Number.isFinite(body.crawlHourKst) ? Math.max(0, Math.min(23, Math.trunc(body.crawlHourKst!))) : current.crawl_hour_kst;
  const now = Date.now();
  await db.prepare("UPDATE news_sources SET is_active = ?, crawl_hour_kst = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?")
    .bind(active ? 1 : 0, hour, nextRunAt(hour, now), now, id).run();
  return Response.json({ ok: true });
}

export async function DELETE(_request: Request, { params }: Context) {
  const id = sourceId((await params).id);
  if (!id) return Response.json({ error: "잘못된 소스 ID입니다." }, { status: 400 });
  const result = await getD1().prepare("DELETE FROM news_sources WHERE id = ?").bind(id).run();
  if (!result.meta.changes) return Response.json({ error: "뉴스 소스를 찾지 못했습니다." }, { status: 404 });
  return Response.json({ ok: true });
}

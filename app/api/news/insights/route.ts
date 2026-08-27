import { getD1 } from "../../../../db";
import { insightQueueStats, processPendingInsights } from "../../../lib/news-insights";

export async function GET() {
  return Response.json(await insightQueueStats(getD1()));
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({})) as { limit?: number };
  const db = getD1();
  try {
    const result = await processPendingInsights(db, Number(body.limit) || 12);
    return Response.json({ ...result, queue: await insightQueueStats(db) });
  } catch (reason) {
    return Response.json({ error: reason instanceof Error ? reason.message : "본문 분석에 실패했습니다." }, { status: 500 });
  }
}

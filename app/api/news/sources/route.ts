import { getD1 } from "../../../../db";
import { crawlSource, validateSourceUrl } from "../../../lib/news-crawler";

type CreateSourceBody = { name?: string; url?: string; symbol?: string; company?: string; crawlHourKst?: number };

export async function GET() {
  const db = getD1();
  const [sources, articles] = await Promise.all([
    db.prepare(`SELECT s.*,
      (SELECT COUNT(*) FROM news_articles a WHERE a.source_id = s.id) AS article_count,
      (SELECT COUNT(*) FROM news_crawl_runs r WHERE r.source_id = s.id) AS run_count
      FROM news_sources s ORDER BY s.is_active DESC, s.created_at DESC`).all(),
    db.prepare(`SELECT a.id, a.source_id, a.symbol, a.title, a.canonical_url, a.published_at, a.collected_at,
      a.sentiment, a.sentiment_score, a.materiality, a.relevance, a.event_type, a.score_adjustment, a.analysis_summary,
      s.name AS source_name
      FROM news_articles a JOIN news_sources s ON s.id = a.source_id
      ORDER BY COALESCE(a.published_at, a.collected_at) DESC LIMIT 40`).all(),
  ]);
  return Response.json({ sources: sources.results, articles: articles.results });
}

export async function POST(request: Request) {
  const body = await request.json() as CreateSourceBody;
  const url = validateSourceUrl(body.url?.trim() ?? "");
  const symbol = body.symbol?.trim().slice(0, 20) ?? "";
  const company = body.company?.trim().slice(0, 100) ?? symbol;
  const name = body.name?.trim().slice(0, 100) || new URL(url).hostname;
  const hour = Number.isFinite(body.crawlHourKst) ? Math.max(0, Math.min(23, Math.trunc(body.crawlHourKst!))) : 6;
  if (!symbol || !company) return Response.json({ error: "분석에 연결할 종목이 필요합니다." }, { status: 400 });

  const db = getD1();
  const now = Date.now();
  try {
    const created = await db.prepare(`INSERT INTO news_sources
      (name, url, symbol, company, crawl_hour_kst, is_active, last_status, next_crawl_at, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 1, '첫 수집 대기', ?, ?, ?) RETURNING id`)
      .bind(name, url, symbol, company, hour, now, now, now).first<{ id: number }>();
    if (!created) throw new Error("소스를 저장하지 못했습니다.");
    try {
      const crawl = await crawlSource(db, created.id);
      return Response.json({ id: created.id, crawl }, { status: 201 });
    } catch (reason) {
      return Response.json({ id: created.id, warning: reason instanceof Error ? reason.message : "첫 수집에 실패했습니다." }, { status: 201 });
    }
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : "뉴스 소스 등록에 실패했습니다.";
    if (/unique|constraint/i.test(message)) return Response.json({ error: "이미 등록된 URL입니다." }, { status: 409 });
    return Response.json({ error: message }, { status: 500 });
  }
}

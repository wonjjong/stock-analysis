import { getD1 } from "../../../../db";
import { crawlSource, dateKst, validateSourceUrl } from "../../../lib/news-crawler";

type CreateSourceBody = { name?: string; url?: string; category?: string; crawlHourKst?: number };

export async function GET() {
  const db = getD1();
  const today = dateKst();
  const [sources, articles] = await Promise.all([
    db.prepare(`SELECT s.id, s.name, s.url, s.resolved_url, s.category, s.crawl_hour_kst, s.is_active,
      s.last_status, s.last_error, s.last_crawled_at, s.next_crawl_at, s.created_at,
      (SELECT COUNT(*) FROM news_articles a WHERE a.source_id = s.id) AS article_count,
      (SELECT COUNT(*) FROM news_articles a WHERE a.source_id = s.id AND a.published_date_kst = ?) AS today_article_count,
      (SELECT COUNT(*) FROM news_crawl_runs r WHERE r.source_id = s.id) AS run_count
      FROM news_sources s ORDER BY s.is_active DESC, s.created_at DESC`).bind(today).all(),
    db.prepare(`SELECT a.id, a.source_id, a.title, a.canonical_url, a.published_at, a.published_date_kst, a.collected_at,
      a.sentiment, a.sentiment_score, a.materiality, a.event_type, a.score_adjustment, a.analysis_summary,
      s.name AS source_name
      FROM news_articles a JOIN news_sources s ON s.id = a.source_id
      WHERE a.published_date_kst = ?
      ORDER BY a.published_at DESC LIMIT 60`).bind(today).all(),
  ]);
  return Response.json({ date: today, sources: sources.results, articles: articles.results });
}

export async function POST(request: Request) {
  const body = await request.json() as CreateSourceBody;
  const url = validateSourceUrl(body.url?.trim() ?? "");
  const name = body.name?.trim().slice(0, 100) || new URL(url).hostname;
  const category = body.category?.trim().slice(0, 30) || "종합";
  const hour = Number.isFinite(body.crawlHourKst) ? Math.max(0, Math.min(23, Math.trunc(body.crawlHourKst!))) : 6;

  const db = getD1();
  const now = Date.now();
  try {
    const created = await db.prepare(`INSERT INTO news_sources
      (name, url, symbol, company, category, crawl_hour_kst, is_active, last_status, next_crawl_at, created_at, updated_at)
      VALUES (?, ?, 'GENERAL', '시장 전체', ?, ?, 1, '첫 수집 대기', ?, ?, ?) RETURNING id`)
      .bind(name, url, category, hour, now, now, now).first<{ id: number }>();
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

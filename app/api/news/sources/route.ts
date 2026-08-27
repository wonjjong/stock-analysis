import { getD1 } from "../../../../db";
import { clampWindowHours, crawlSource, dateKst, DEFAULT_WINDOW_HOURS, validateSourceUrl } from "../../../lib/news-crawler";

type CreateSourceBody = { name?: string; url?: string; category?: string; crawlHourKst?: number; maxPages?: number; windowHours?: number };

// The listing mirrors the crawler: recently published rather than same-day, so
// a US wire filed late in its own evening still shows up here.
const RECENT_LIST_HOURS = 48;

// 컬럼이 timestamptz이므로 SQL 경계에서만 Date로 바꾼다.
const at = (ms: number) => new Date(ms);

export async function GET() {
  const db = getD1();
  const now = Date.now();
  const since = now - RECENT_LIST_HOURS * 60 * 60 * 1000;
  const [sources, articles] = await Promise.all([
    db.prepare(`SELECT s.id, s.name, s.url, s.resolved_url, s.category, s.crawl_hour_kst, s.is_active,
      s.last_status, s.last_error, s.last_crawled_at, s.next_crawl_at, s.created_at, s.max_pages, s.window_hours,
      (SELECT COUNT(*) FROM news_articles a WHERE a.source_id = s.id) AS article_count,
      (SELECT COUNT(*) FROM news_articles a WHERE a.source_id = s.id AND a.published_at >= ?) AS recent_article_count,
      (SELECT COUNT(*) FROM news_crawl_runs r WHERE r.source_id = s.id) AS run_count
      FROM news_sources s ORDER BY s.is_active DESC, s.created_at DESC`).bind(at(since)).all(),
    db.prepare(`SELECT a.id, a.source_id, a.title, a.canonical_url, a.published_at, a.published_date_kst, a.collected_at,
      a.sentiment, a.sentiment_score, a.materiality, a.event_type, a.score_adjustment, a.analysis_summary,
      s.name AS source_name
      FROM news_articles a JOIN news_sources s ON s.id = a.source_id
      WHERE a.published_at >= ?
      ORDER BY a.published_at DESC LIMIT 80`).bind(at(since)).all(),
  ]);
  return Response.json({ date: dateKst(now), windowHours: RECENT_LIST_HOURS, sources: sources.results, articles: articles.results });
}

export async function POST(request: Request) {
  const body = await request.json() as CreateSourceBody;
  const url = validateSourceUrl(body.url?.trim() ?? "");
  const name = body.name?.trim().slice(0, 100) || new URL(url).hostname;
  const category = body.category?.trim().slice(0, 30) || "종합";
  const hour = Number.isFinite(body.crawlHourKst) ? Math.max(0, Math.min(23, Math.trunc(body.crawlHourKst!))) : 6;
  const maxPages = Number.isFinite(body.maxPages) ? Math.max(1, Math.min(10, Math.trunc(body.maxPages!))) : 1;
  const windowHours = Number.isFinite(body.windowHours) ? clampWindowHours(body.windowHours!) : DEFAULT_WINDOW_HOURS;

  const db = getD1();
  const now = Date.now();
  try {
    const created = await db.prepare(`INSERT INTO news_sources
      (name, url, symbol, company, category, crawl_hour_kst, max_pages, window_hours, is_active, last_status, next_crawl_at, created_at, updated_at)
      VALUES (?, ?, 'GENERAL', '시장 전체', ?, ?, ?, ?, true, '첫 수집 대기', ?, ?, ?) RETURNING id`)
      .bind(name, url, category, hour, maxPages, windowHours, at(now), at(now), at(now)).first<{ id: number }>();
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

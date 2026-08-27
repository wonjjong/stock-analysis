import { getD1 } from "../../../../db";

const PAGE_SIZE = 30;
const MAX_PAGE_SIZE = 100;
// published_date_kst는 DB 생성 열이다. 빈 문자열로 남는 행이 없으므로 되살릴 필요가 없고
// 인덱스도 그대로 쓰인다.
const DATE_KST = `a.published_date_kst`;
const SENTIMENTS = ["긍정", "부정", "중립"];

type ArticleRow = { id: number } & Record<string, unknown>;
type SymbolTag = { article_id: number; symbol: string; company: string; market: string; sector: string; relevance: number };

function isDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function likeTerm(value: string) {
  return `%${value.replace(/[\\%_]/g, (match) => `\\${match}`)}%`;
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const conditions: string[] = [];
  const values: (string | number)[] = [];

  const from = params.get("from")?.trim() ?? "";
  const to = params.get("to")?.trim() ?? "";
  if (isDate(from)) { conditions.push(`${DATE_KST} >= ?`); values.push(from); }
  if (isDate(to)) { conditions.push(`${DATE_KST} <= ?`); values.push(to); }

  const sourceId = Number(params.get("source"));
  if (Number.isInteger(sourceId) && sourceId > 0) { conditions.push("a.source_id = ?"); values.push(sourceId); }

  const sentiment = params.get("sentiment")?.trim() ?? "";
  if (SENTIMENTS.includes(sentiment)) { conditions.push("a.sentiment = ?"); values.push(sentiment); }

  const symbol = params.get("symbol")?.trim().slice(0, 20) ?? "";
  if (symbol) { conditions.push("EXISTS (SELECT 1 FROM news_article_symbols m WHERE m.article_id = a.id AND m.symbol = ?)"); values.push(symbol); }

  const query = params.get("q")?.trim().slice(0, 80) ?? "";
  if (query) {
    // keywords는 jsonb다. 예전에는 직렬화된 JSON 텍스트를 LIKE로 훑어 구두점까지
    // 검색 대상이 되고 배열 원소 경계를 넘어 매칭됐다(예: '노조","대비'). 원소를
    // 펼쳐 각각과 비교하면 그 부류의 오탐이 사라진다.
    conditions.push(`(a.title LIKE ? ESCAPE '\\' OR a.excerpt LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\'
      OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(i.keywords) AS kw WHERE kw LIKE ? ESCAPE '\\'))`);
    values.push(likeTerm(query), likeTerm(query), likeTerm(query), likeTerm(query));
  }

  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const size = Math.max(1, Math.min(MAX_PAGE_SIZE, Number(params.get("size")) || PAGE_SIZE));
  const page = Math.max(1, Math.trunc(Number(params.get("page")) || 1));

  const db = getD1();
  const [summary, articles, sources, topSymbols] = await Promise.all([
    db.prepare(`SELECT COUNT(*) AS total,
      SUM(CASE WHEN a.sentiment = '긍정' THEN 1 ELSE 0 END) AS positive,
      SUM(CASE WHEN a.sentiment = '부정' THEN 1 ELSE 0 END) AS negative,
      MIN(${DATE_KST}) AS first_date, MAX(${DATE_KST}) AS last_date,
      SUM(CASE WHEN a.insight_status = '대기' THEN 1 ELSE 0 END) AS pending
      FROM news_articles a LEFT JOIN news_insights i ON i.article_id = a.id ${where}`).bind(...values).first<{ total: number; positive: number; negative: number; first_date: string | null; last_date: string | null; pending: number }>(),
    db.prepare(`SELECT a.id, a.source_id, a.title, a.canonical_url, a.excerpt, a.published_at, a.collected_at,
      ${DATE_KST} AS date_kst, a.sentiment, a.sentiment_score, a.materiality, a.relevance,
      a.event_type, a.score_adjustment, a.insight_status, s.name AS source_name, s.category AS source_category,
      i.summary, i.keywords, i.sectors, i.evidence, i.market_view, i.impact_horizon, i.engine, i.model, i.body_chars
      FROM news_articles a JOIN news_sources s ON s.id = a.source_id LEFT JOIN news_insights i ON i.article_id = a.id ${where}
      ORDER BY COALESCE(a.published_at, a.collected_at) DESC, a.id DESC LIMIT ? OFFSET ?`)
      .bind(...values, size, (page - 1) * size).all<ArticleRow>(),
    db.prepare(`SELECT s.id, s.name, s.category, COUNT(a.id) AS article_count
      FROM news_sources s LEFT JOIN news_articles a ON a.source_id = s.id
      GROUP BY s.id ORDER BY article_count DESC, s.name`).all(),
    // Postgres는 GROUP BY에 없는 컬럼 선택을 거부한다(SQLite는 허용했다). symbol은 PK가
    // 아니므로 함수종속이 성립하지 않아 company·market을 함께 묶는다.
    db.prepare(`SELECT symbol, company, market, COUNT(*) AS article_count FROM news_article_symbols
      GROUP BY symbol, company, market ORDER BY article_count DESC, company LIMIT 40`).all(),
  ]);

  const ids = articles.results.map((row: ArticleRow) => row.id);
  const tags = ids.length
    ? await db.prepare(`SELECT article_id, symbol, company, market, sector, relevance FROM news_article_symbols
        WHERE article_id IN (${ids.map(() => "?").join(",")}) ORDER BY relevance DESC`).bind(...ids).all<SymbolTag>()
    : { results: [] as SymbolTag[] };
  const byArticle = new Map<number, SymbolTag[]>();
  for (const tag of tags.results) {
    const list = byArticle.get(tag.article_id) ?? [];
    list.push(tag);
    byArticle.set(tag.article_id, list);
  }

  const total = summary?.total ?? 0;
  return Response.json({
    articles: articles.results.map((row: ArticleRow) => ({ ...row, symbols: byArticle.get(row.id) ?? [] })),
    sources: sources.results,
    topSymbols: topSymbols.results,
    summary: { total, positive: summary?.positive ?? 0, negative: summary?.negative ?? 0, pending: summary?.pending ?? 0, firstDate: summary?.first_date ?? null, lastDate: summary?.last_date ?? null },
    page, size, pageCount: Math.max(1, Math.ceil(total / size)),
  });
}

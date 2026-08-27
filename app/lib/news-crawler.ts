import { analyzeNewsLocally } from "./news-analysis";

const MAX_FEED_BYTES = 2_500_000;
const MAX_ITEMS_PER_RUN = 60;
const USER_AGENT = "SignalistResearchBot/1.0 (+daily RSS reader; owner-managed sources)";

type SourceRow = {
  id: number;
  name: string;
  url: string;
  resolved_url: string | null;
  symbol: string;
  company: string;
  crawl_hour_kst: number;
  etag: string | null;
  last_modified: string | null;
};

export type FeedItem = {
  title: string;
  url: string;
  excerpt: string;
  publishedAt: number | null;
};

export type CrawlResult = {
  sourceId: number;
  fetchedCount: number;
  insertedCount: number;
  status: "완료" | "변경 없음";
};

function decodeXml(value: string) {
  const entities: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  return value.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1").replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (_, entity: string) => {
    if (entity[0] === "#") {
      const hex = entity[1]?.toLowerCase() === "x";
      const value = Number.parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10);
      return Number.isFinite(value) ? String.fromCodePoint(value) : "";
    }
    return entities[entity.toLowerCase()] ?? `&${entity};`;
  });
}

function cleanText(value: string, max = 6000) {
  return decodeXml(value)
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

function tag(block: string, names: string[]) {
  for (const name of names) {
    const match = block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`, "i"));
    if (match?.[1]) return match[1];
  }
  return "";
}

function absoluteArticleUrl(value: string, baseUrl: string) {
  try {
    const url = new URL(decodeXml(value).trim(), baseUrl);
    url.hash = "";
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"].forEach((key) => url.searchParams.delete(key));
    return url.toString();
  } catch {
    return "";
  }
}

function parseDate(value: string) {
  const time = Date.parse(cleanText(value, 120));
  return Number.isFinite(time) ? time : null;
}

export function parseFeed(xml: string, feedUrl: string): FeedItem[] {
  const rssBlocks = [...xml.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)].map((match) => match[1]);
  const atomBlocks = [...xml.matchAll(/<entry(?:\s[^>]*)?>([\s\S]*?)<\/entry>/gi)].map((match) => match[1]);
  const blocks = rssBlocks.length ? rssBlocks : atomBlocks;

  return blocks.slice(0, MAX_ITEMS_PER_RUN).flatMap((block) => {
    const title = cleanText(tag(block, ["title"]), 500);
    const rssLink = tag(block, ["link", "guid"]);
    const atomHref = block.match(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*>/i)?.[1] ?? "";
    const url = absoluteArticleUrl(atomHref || cleanText(rssLink, 2000), feedUrl);
    const excerpt = cleanText(tag(block, ["content:encoded", "content", "description", "summary"]));
    const publishedAt = parseDate(tag(block, ["pubDate", "published", "updated", "dc:date"]));
    return title && url ? [{ title, url, excerpt, publishedAt }] : [];
  });
}

function isPrivateIpv4(hostname: string) {
  const parts = hostname.split(".");
  if (parts.length !== 4 || parts.some((part) => !/^\d+$/.test(part))) return false;
  const nums = parts.map(Number);
  if (nums.some((value) => value < 0 || value > 255)) return true;
  return nums[0] === 10 || nums[0] === 127 || nums[0] === 0 ||
    (nums[0] === 169 && nums[1] === 254) || (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31) ||
    (nums[0] === 192 && nums[1] === 168) || nums[0] >= 224;
}

export function validateSourceUrl(value: string) {
  let url: URL;
  try { url = new URL(value); } catch { throw new Error("올바른 뉴스 URL을 입력해 주세요."); }
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("HTTP 또는 HTTPS URL만 등록할 수 있습니다.");
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (url.username || url.password || !host || host === "localhost" || host.endsWith(".local") || host.endsWith(".internal") || /^\d+$/.test(host) || /^0x[0-9a-f]+$/i.test(host) || isPrivateIpv4(host) || host.includes(":")) {
    throw new Error("내부 네트워크 주소는 등록할 수 없습니다.");
  }
  url.hash = "";
  return url.toString();
}

async function readLimited(response: Response) {
  const declared = Number(response.headers.get("content-length") ?? 0);
  if (declared > MAX_FEED_BYTES) throw new Error("피드 크기가 2.5MB를 초과합니다.");
  const reader = response.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_FEED_BYTES) { await reader.cancel(); throw new Error("피드 크기가 2.5MB를 초과합니다."); }
    chunks.push(value);
  }
  const combined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { combined.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(combined);
}

async function safeFetch(input: string, headers: HeadersInit = {}) {
  let current = validateSourceUrl(input);
  for (let redirects = 0; redirects <= 3; redirects += 1) {
    const response = await fetch(current, {
      headers: { "User-Agent": USER_AGENT, Accept: "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8", ...headers },
      redirect: "manual",
      signal: AbortSignal.timeout(12_000),
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get("location");
      if (!location) throw new Error("리다이렉트 위치가 없습니다.");
      current = validateSourceUrl(new URL(location, current).toString());
      continue;
    }
    return { response, finalUrl: current };
  }
  throw new Error("리다이렉트가 너무 많습니다.");
}

function looksLikeFeed(text: string) {
  return /<(rss|feed|rdf:RDF)\b/i.test(text) && /<(item|entry)\b/i.test(text);
}

async function fetchFeed(source: SourceRow) {
  const conditionalHeaders: Record<string, string> = {};
  if (source.etag) conditionalHeaders["If-None-Match"] = source.etag;
  if (source.last_modified) conditionalHeaders["If-Modified-Since"] = source.last_modified;
  const preferred = source.resolved_url || source.url;
  let fetched = await safeFetch(preferred, conditionalHeaders);
  if (fetched.response.status === 304) return { unchanged: true as const, url: fetched.finalUrl, response: fetched.response, text: "" };
  if (!fetched.response.ok) throw new Error(`뉴스 소스 응답 오류 (${fetched.response.status})`);
  let text = await readLimited(fetched.response);
  if (looksLikeFeed(text)) return { unchanged: false as const, url: fetched.finalUrl, response: fetched.response, text };

  const feedHref = text.match(/<link\b[^>]*\btype=["']application\/(?:rss|atom)\+xml["'][^>]*\bhref=["']([^"']+)["'][^>]*>/i)?.[1]
    ?? text.match(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\btype=["']application\/(?:rss|atom)\+xml["'][^>]*>/i)?.[1];
  if (!feedHref) throw new Error("RSS/Atom 피드를 찾지 못했습니다. 뉴스 사이트의 RSS 주소를 등록해 주세요.");
  const discoveredUrl = validateSourceUrl(new URL(decodeXml(feedHref), fetched.finalUrl).toString());
  fetched = await safeFetch(discoveredUrl);
  if (!fetched.response.ok) throw new Error(`발견한 피드 응답 오류 (${fetched.response.status})`);
  text = await readLimited(fetched.response);
  if (!looksLikeFeed(text)) throw new Error("등록한 주소가 RSS/Atom 형식이 아닙니다.");
  return { unchanged: false as const, url: fetched.finalUrl, response: fetched.response, text };
}

async function hash(value: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function nextRunAt(hourKst: number, now = Date.now()) {
  const safeHour = Math.max(0, Math.min(23, Math.trunc(hourKst)));
  const kst = new Date(now + 9 * 60 * 60 * 1000);
  let target = Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate(), safeHour - 9, 0, 0, 0);
  if (target <= now) target += 24 * 60 * 60 * 1000;
  return target;
}

function errorMessage(reason: unknown) {
  if (reason instanceof Error) return reason.name === "TimeoutError" ? "응답 시간이 12초를 초과했습니다." : reason.message.slice(0, 500);
  return "알 수 없는 수집 오류가 발생했습니다.";
}

export async function crawlSource(db: D1Database, sourceId: number): Promise<CrawlResult> {
  const source = await db.prepare("SELECT * FROM news_sources WHERE id = ? AND is_active = 1").bind(sourceId).first<SourceRow>();
  if (!source) throw new Error("활성화된 뉴스 소스를 찾지 못했습니다.");
  const startedAt = Date.now();
  const run = await db.prepare("INSERT INTO news_crawl_runs (source_id, status, started_at) VALUES (?, '실행 중', ?) RETURNING id").bind(source.id, startedAt).first<{ id: number }>();
  if (!run) throw new Error("수집 실행 이력을 만들지 못했습니다.");
  try {
    const feed = await fetchFeed(source);
    const next = nextRunAt(source.crawl_hour_kst, startedAt);
    if (feed.unchanged) {
      await db.batch([
        db.prepare("UPDATE news_sources SET last_status = '변경 없음', last_error = NULL, last_crawled_at = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?").bind(startedAt, next, startedAt, source.id),
        db.prepare("UPDATE news_crawl_runs SET status = '변경 없음', completed_at = ? WHERE id = ?").bind(Date.now(), run.id),
      ]);
      return { sourceId, fetchedCount: 0, insertedCount: 0, status: "변경 없음" };
    }
    const items = parseFeed(feed.text, feed.url);
    if (!items.length) throw new Error("피드에서 기사 항목을 읽지 못했습니다.");
    let insertedCount = 0;
    for (const item of items) {
      const contentHash = await hash(`${item.title}\n${item.excerpt}`);
      const analysisText = `${item.title}. ${item.excerpt}`.slice(0, 6500);
      const analysis = analyzeNewsLocally(analysisText, source.symbol, source.company);
      const result = await db.prepare(`INSERT OR IGNORE INTO news_articles
        (source_id, symbol, title, canonical_url, excerpt, published_at, content_hash, sentiment, sentiment_score, materiality, relevance, event_type, score_adjustment, analysis_summary, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(source.id, source.symbol, item.title, item.url, item.excerpt, item.publishedAt, contentHash, analysis.sentiment, Math.round(analysis.sentimentScore), analysis.materiality, Math.round(analysis.relevance), analysis.eventType, analysis.scoreAdjustment, analysis.summary, startedAt).run();
      insertedCount += result.meta.changes ?? 0;
    }
    await db.batch([
      db.prepare("UPDATE news_sources SET resolved_url = ?, etag = ?, last_modified = ?, last_status = '완료', last_error = NULL, last_crawled_at = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?")
        .bind(feed.url, feed.response.headers.get("etag"), feed.response.headers.get("last-modified"), startedAt, next, startedAt, source.id),
      db.prepare("UPDATE news_crawl_runs SET status = '완료', fetched_count = ?, inserted_count = ?, completed_at = ? WHERE id = ?")
        .bind(items.length, insertedCount, Date.now(), run.id),
    ]);
    return { sourceId, fetchedCount: items.length, insertedCount, status: "완료" };
  } catch (reason) {
    const message = errorMessage(reason);
    await db.batch([
      db.prepare("UPDATE news_sources SET last_status = '오류', last_error = ?, last_crawled_at = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?")
        .bind(message, startedAt, nextRunAt(source.crawl_hour_kst, startedAt), startedAt, source.id),
      db.prepare("UPDATE news_crawl_runs SET status = '오류', error = ?, completed_at = ? WHERE id = ?").bind(message, Date.now(), run.id),
    ]);
    throw new Error(message);
  }
}

export async function crawlDueSources(db: D1Database) {
  const due = await db.prepare("SELECT id FROM news_sources WHERE is_active = 1 AND next_crawl_at <= ? ORDER BY next_crawl_at LIMIT 20").bind(Date.now()).all<{ id: number }>();
  const results: Array<CrawlResult | { sourceId: number; error: string }> = [];
  for (const source of due.results) {
    try { results.push(await crawlSource(db, source.id)); }
    catch (reason) { results.push({ sourceId: source.id, error: errorMessage(reason) }); }
  }
  await db.prepare("PRAGMA optimize").run();
  return results;
}

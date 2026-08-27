import { analyzeNewsLocally } from "./news-analysis";

const MAX_FEED_BYTES = 2_500_000;
const MAX_ITEMS_PER_RUN = 60;
const USER_AGENT = "SignalistResearchBot/1.1 (+daily public news indexer; owner-managed sources)";

type SourceRow = {
  id: number;
  name: string;
  url: string;
  resolved_url: string | null;
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
  status: "완료" | "변경 없음" | "오늘 기사 없음";
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

export function dateKst(time = Date.now()) {
  return new Date(time + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function parseVisibleDate(value: string, now = Date.now()) {
  const compact = cleanText(value, 400);
  if (!compact) return null;
  if (/오늘|today/i.test(compact)) return now;
  const relative = compact.match(/(\d+)\s*(분|시간|minute|minutes|hour|hours)\s*(전|ago)?/i);
  if (relative) {
    const unit = /분|minute/i.test(relative[2]) ? 60_000 : 3_600_000;
    return now - Number(relative[1]) * unit;
  }
  if (/T\d{2}:\d{2}|(?:GMT|UTC)|Z(?:\s|$)|[+-]\d{2}:?\d{2}/i.test(compact)) {
    const zoned = Date.parse(compact);
    if (Number.isFinite(zoned)) return zoned;
  }
  const isoLike = compact.match(/(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?:\s+|T)?(\d{1,2})?:?(\d{2})?/);
  if (isoLike) return Date.UTC(Number(isoLike[1]), Number(isoLike[2]) - 1, Number(isoLike[3]), Number(isoLike[4] ?? 0) - 9, Number(isoLike[5] ?? 0));
  const short = compact.match(/(?:^|\s)(\d{1,2})[./-](\d{1,2})(?:\s+(\d{1,2}):?(\d{2})?)?/);
  if (short) {
    const current = new Date(now + 9 * 60 * 60 * 1000);
    return Date.UTC(current.getUTCFullYear(), Number(short[1]) - 1, Number(short[2]), Number(short[3] ?? 0) - 9, Number(short[4] ?? 0));
  }
  const korean = compact.match(/(\d{1,2})월\s*(\d{1,2})일(?:\s*(\d{1,2})시)?/);
  if (korean) {
    const current = new Date(now + 9 * 60 * 60 * 1000);
    return Date.UTC(current.getUTCFullYear(), Number(korean[1]) - 1, Number(korean[2]), Number(korean[3] ?? 0) - 9);
  }
  const parsed = Date.parse(compact);
  return Number.isFinite(parsed) ? parsed : null;
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

function articleType(value: unknown) {
  const types = Array.isArray(value) ? value : [value];
  return types.some((type) => typeof type === "string" && /NewsArticle|Article|ReportageNewsArticle/i.test(type));
}

function jsonLdItems(html: string, pageUrl: string): FeedItem[] {
  const items: FeedItem[] = [];
  const visit = (value: unknown) => {
    if (Array.isArray(value)) { value.forEach(visit); return; }
    if (!value || typeof value !== "object") return;
    const item = value as Record<string, unknown>;
    if (articleType(item["@type"])) {
      const title = cleanText(String(item.headline ?? item.name ?? ""), 500);
      const main = item.mainEntityOfPage;
      const link = typeof item.url === "string" ? item.url : typeof main === "string" ? main : main && typeof main === "object" ? String((main as Record<string, unknown>)["@id"] ?? "") : "";
      const publishedAt = parseVisibleDate(String(item.datePublished ?? item.dateCreated ?? ""));
      const url = absoluteArticleUrl(link, pageUrl);
      if (title && url && publishedAt) items.push({ title, url, excerpt: cleanText(String(item.description ?? "")), publishedAt });
    }
    Object.values(item).forEach(visit);
  };
  for (const match of html.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)) {
    try { visit(JSON.parse(decodeXml(match[1]).trim())); } catch { /* malformed publisher metadata */ }
  }
  return items;
}

function dateFromHtml(block: string, now = Date.now()) {
  const attribute = block.match(/<(?:time|meta)\b[^>]*(?:datetime|content|data-date|data-published)=["']([^"']+)["'][^>]*>/i)?.[1];
  return parseVisibleDate(attribute || block, now);
}

function anchorItem(block: string, pageUrl: string, now: number): FeedItem | null {
  const anchors = [...block.matchAll(/<a\b([^>]*)href=["']([^"']+)["']([^>]*)>([\s\S]*?)<\/a>/gi)];
  const ranked = anchors.map((match) => {
    const attributes = `${match[1]} ${match[3]}`;
    const visibleTitle = cleanText(match[4], 500);
    const title = visibleTitle || cleanText(attributes.match(/title=["']([^"']+)["']/i)?.[1] || "", 500);
    return { title, href: match[2] };
  }).filter((item) => item.title.length >= 12 && !/^(로그인|구독|더보기|전체보기|메뉴|홈|login|subscribe|read more)$/i.test(item.title)).sort((a, b) => b.title.length - a.title.length);
  const best = ranked[0];
  const publishedAt = dateFromHtml(block, now);
  const url = best ? absoluteArticleUrl(best.href, pageUrl) : "";
  if (!best || !url || !publishedAt) return null;
  return { title: best.title, url, excerpt: cleanText(block, 1200).replace(best.title, "").trim(), publishedAt };
}

export function parseNewsPage(html: string, pageUrl: string, now = Date.now()): FeedItem[] {
  const candidates = jsonLdItems(html, pageUrl);
  for (const match of html.matchAll(/<(article|li)\b[^>]*>([\s\S]*?)<\/\1>/gi)) {
    const item = anchorItem(match[2], pageUrl, now);
    if (item) candidates.push(item);
  }
  for (const match of html.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
    const title = cleanText(match[2], 500);
    if (title.length < 12) continue;
    const index = match.index ?? 0;
    const context = html.slice(Math.max(0, index - 320), Math.min(html.length, index + match[0].length + 320));
    const publishedAt = dateFromHtml(context, now);
    const url = absoluteArticleUrl(match[1], pageUrl);
    if (url && publishedAt) candidates.push({ title, url, excerpt: "", publishedAt });
  }
  const unique = new Map<string, FeedItem>();
  for (const item of candidates) if (!unique.has(item.url)) unique.set(item.url, item);
  return [...unique.values()].slice(0, MAX_ITEMS_PER_RUN);
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

type RobotsRule = { allow: boolean; pattern: string };

function robotsAllows(text: string, target: URL) {
  const exact: RobotsRule[] = [];
  const fallback: RobotsRule[] = [];
  let agents: string[] = [];
  let hasDirectives = false;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/\s*#.*$/, "").trim();
    if (!line) { agents = []; hasDirectives = false; continue; }
    const separator = line.indexOf(":");
    if (separator < 0) continue;
    const key = line.slice(0, separator).trim().toLowerCase();
    const value = line.slice(separator + 1).trim();
    if (key === "user-agent") {
      if (hasDirectives) agents = [];
      agents.push(value.toLowerCase()); hasDirectives = false; continue;
    }
    if (key !== "allow" && key !== "disallow") continue;
    hasDirectives = true;
    if (!value) continue;
    const rule = { allow: key === "allow", pattern: value };
    if (agents.some((agent) => "signalistresearchbot".startsWith(agent) || agent.startsWith("signalistresearchbot"))) exact.push(rule);
    else if (agents.includes("*")) fallback.push(rule);
  }
  const rules = exact.length ? exact : fallback;
  const path = `${target.pathname}${target.search}`;
  const matches = rules.filter((rule) => {
    const escaped = rule.pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\\\$$/, "$");
    try { return new RegExp(`^${escaped}`).test(path); } catch { return path.startsWith(rule.pattern); }
  }).sort((a, b) => b.pattern.length - a.pattern.length || Number(b.allow) - Number(a.allow));
  return matches[0]?.allow ?? true;
}

async function assertRobotsAllowed(input: string) {
  const target = new URL(validateSourceUrl(input));
  const robotsUrl = `${target.origin}/robots.txt`;
  const { response } = await safeFetch(robotsUrl, { Accept: "text/plain" });
  if (response.status === 401 || response.status === 403) throw new Error("이 사이트의 robots.txt가 자동 수집을 허용하지 않습니다.");
  if (response.status >= 500) throw new Error("robots.txt를 확인할 수 없어 이번 수집을 보류했습니다.");
  if (!response.ok) return;
  const rules = await readLimited(response);
  if (!robotsAllows(rules, target)) throw new Error("이 URL은 사이트의 robots.txt에서 자동 수집을 허용하지 않습니다.");
}

function looksLikeFeed(text: string) {
  return /<(rss|feed|rdf:RDF)\b/i.test(text) && /<(item|entry)\b/i.test(text);
}

async function fetchSourceItems(source: SourceRow, now: number) {
  const conditionalHeaders: Record<string, string> = {};
  if (source.etag) conditionalHeaders["If-None-Match"] = source.etag;
  if (source.last_modified) conditionalHeaders["If-Modified-Since"] = source.last_modified;
  const preferred = source.resolved_url || source.url;
  await assertRobotsAllowed(preferred);
  let fetched = await safeFetch(preferred, conditionalHeaders);
  if (fetched.response.status === 304) return { unchanged: true as const, url: fetched.finalUrl, response: fetched.response, items: [] as FeedItem[] };
  if (!fetched.response.ok) throw new Error(`뉴스 소스 응답 오류 (${fetched.response.status})`);
  let text = await readLimited(fetched.response);
  if (looksLikeFeed(text)) return { unchanged: false as const, url: fetched.finalUrl, response: fetched.response, items: parseFeed(text, fetched.finalUrl) };

  const pageUrl = fetched.finalUrl;
  const pageResponse = fetched.response;
  const htmlItems = parseNewsPage(text, fetched.finalUrl, now);

  const feedHref = text.match(/<link\b[^>]*\btype=["']application\/(?:rss|atom)\+xml["'][^>]*\bhref=["']([^"']+)["'][^>]*>/i)?.[1]
    ?? text.match(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\btype=["']application\/(?:rss|atom)\+xml["'][^>]*>/i)?.[1];
  if (!feedHref) {
    if (!htmlItems.length) throw new Error("오늘 날짜를 식별할 수 있는 기사 목록을 찾지 못했습니다. RSS 또는 날짜가 표시된 뉴스 목록 URL을 등록해 주세요.");
    return { unchanged: false as const, url: pageUrl, response: pageResponse, items: htmlItems };
  }
  const discoveredUrl = validateSourceUrl(new URL(decodeXml(feedHref), fetched.finalUrl).toString());
  try {
    await assertRobotsAllowed(discoveredUrl);
    fetched = await safeFetch(discoveredUrl);
    if (!fetched.response.ok) throw new Error(`발견한 피드 응답 오류 (${fetched.response.status})`);
    text = await readLimited(fetched.response);
    const feedItems = looksLikeFeed(text) ? parseFeed(text, fetched.finalUrl) : [];
    if (feedItems.length) return { unchanged: false as const, url: fetched.finalUrl, response: fetched.response, items: feedItems };
  } catch {
    if (!htmlItems.length) throw new Error("페이지에서 발견한 RSS를 읽지 못했고 HTML 기사 날짜도 식별하지 못했습니다.");
  }
  if (!htmlItems.length) throw new Error("뉴스 기사와 발행일을 식별하지 못했습니다.");
  return { unchanged: false as const, url: pageUrl, response: pageResponse, items: htmlItems };
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
    const fetched = await fetchSourceItems(source, startedAt);
    const next = nextRunAt(source.crawl_hour_kst, startedAt);
    if (fetched.unchanged) {
      await db.batch([
        db.prepare("UPDATE news_sources SET last_status = '변경 없음', last_error = NULL, last_crawled_at = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?").bind(startedAt, next, startedAt, source.id),
        db.prepare("UPDATE news_crawl_runs SET status = '변경 없음', completed_at = ? WHERE id = ?").bind(Date.now(), run.id),
      ]);
      return { sourceId, fetchedCount: 0, insertedCount: 0, status: "변경 없음" };
    }
    const today = dateKst(startedAt);
    const items = fetched.items.filter((item) => item.publishedAt !== null && dateKst(item.publishedAt) === today);
    const completedStatus = items.length ? "완료" : "오늘 기사 없음";
    let insertedCount = 0;
    for (const item of items) {
      const contentHash = await hash(`${item.title}\n${item.excerpt}`);
      const analysisText = `${item.title}. ${item.excerpt}`.slice(0, 6500);
      const analysis = analyzeNewsLocally(analysisText, "MARKET", "시장 전체");
      const result = await db.prepare(`INSERT OR IGNORE INTO news_articles
        (source_id, symbol, title, canonical_url, excerpt, published_at, published_date_kst, content_hash, sentiment, sentiment_score, materiality, relevance, event_type, score_adjustment, analysis_summary, collected_at)
        VALUES (?, 'GENERAL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(source.id, item.title, item.url, item.excerpt, item.publishedAt, today, contentHash, analysis.sentiment, Math.round(analysis.sentimentScore), analysis.materiality, 100, analysis.eventType, analysis.scoreAdjustment, analysis.summary, startedAt).run();
      insertedCount += result.meta.changes ?? 0;
    }
    await db.batch([
      db.prepare("UPDATE news_sources SET resolved_url = ?, etag = ?, last_modified = ?, last_status = ?, last_error = NULL, last_crawled_at = ?, next_crawl_at = ?, updated_at = ? WHERE id = ?")
        .bind(fetched.url, fetched.response.headers.get("etag"), fetched.response.headers.get("last-modified"), completedStatus, startedAt, next, startedAt, source.id),
      db.prepare("UPDATE news_crawl_runs SET status = ?, fetched_count = ?, inserted_count = ?, completed_at = ? WHERE id = ?")
        .bind(completedStatus, items.length, insertedCount, Date.now(), run.id),
    ]);
    return { sourceId, fetchedCount: items.length, insertedCount, status: completedStatus };
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

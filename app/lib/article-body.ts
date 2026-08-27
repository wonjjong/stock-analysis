import { robotsAllows, validateSourceUrl } from "./news-crawler";

const USER_AGENT = "SignalistResearchBot/1.1 (+daily public news indexer; owner-managed sources)";
const MAX_BYTES = 1_500_000;
const MAX_BODY_CHARS = 9_000;
const MIN_PARAGRAPH_CHARS = 20;
/** 언론사 페이지 하단의 저작권·제보·구독 안내는 본문이 아니라 잡음이다. */
const boilerplate = /저작권자|무단\s*전재|재배포\s*금지|제보는|구독하기|기사제보|All rights reserved|Copyright ⓒ/i;

export type ArticleBody = { text: string; chars: number; finalUrl: string; source: "본문" | "요약" };

function stripNoise(html: string) {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style|noscript|iframe|svg|form|nav|header|footer|aside)\b[^>]*>[\s\S]*?<\/\1>/gi, " ");
}

function decodeEntities(value: string) {
  const named: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  return value.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (_, entity: string) => {
    if (entity[0] === "#") {
      const hex = entity[1]?.toLowerCase() === "x";
      const code = Number.parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : "";
    }
    return named[entity.toLowerCase()] ?? " ";
  });
}

function text(html: string) {
  return decodeEntities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
}

/** 문단 태그를 모아 본문을 만든다. 문단이 없으면 가장 글자가 많은 블록으로 대체한다. */
export function extractBody(html: string) {
  const clean = stripNoise(html);
  const paragraphs = [...clean.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)]
    .map((match) => text(match[1]))
    .filter((value) => value.length >= MIN_PARAGRAPH_CHARS && !boilerplate.test(value));
  if (paragraphs.length >= 2) return paragraphs.join("\n").slice(0, MAX_BODY_CHARS);

  const blocks = [...clean.matchAll(/<(article|section|div)\b[^>]*>([\s\S]*?)<\/\1>/gi)]
    .map((match) => text(match[2]))
    .sort((left, right) => right.length - left.length);
  const best = blocks[0] ?? text(clean);
  return best.slice(0, MAX_BODY_CHARS);
}

async function readLimited(response: Response) {
  const reader = response.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BYTES) { await reader.cancel(); break; }
    chunks.push(value);
  }
  const combined = new Uint8Array(chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0));
  let offset = 0;
  for (const chunk of chunks) { combined.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(combined);
}

async function allowedByRobots(target: URL, cache: Map<string, string>) {
  const cached = cache.get(target.origin);
  if (cached !== undefined) return robotsAllows(cached, target);
  try {
    const response = await fetch(`${target.origin}/robots.txt`, {
      headers: { "User-Agent": USER_AGENT, Accept: "text/plain" },
      signal: AbortSignal.timeout(8_000),
    });
    // 401·403·5xx는 판단 불가로 보고 수집하지 않는다.
    if (response.status === 401 || response.status === 403 || response.status >= 500) { cache.set(target.origin, "User-agent: *\nDisallow: /"); return false; }
    const rules = response.ok ? (await response.text()).slice(0, 200_000) : "";
    cache.set(target.origin, rules);
    return robotsAllows(rules, target);
  } catch {
    cache.set(target.origin, "");
    return true;
  }
}

/** 기사 원문 페이지에서 본문 텍스트만 가져온다. 원문은 저장하지 않고 분석 입력으로만 쓴다. */
export async function fetchArticleBody(url: string, robotsCache = new Map<string, string>()): Promise<ArticleBody> {
  let current = validateSourceUrl(url);
  for (let redirects = 0; redirects <= 3; redirects += 1) {
    const target = new URL(current);
    if (!await allowedByRobots(target, robotsCache)) throw new Error("robots.txt가 본문 수집을 허용하지 않습니다.");
    const response = await fetch(current, {
      headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml" },
      redirect: "manual",
      signal: AbortSignal.timeout(12_000),
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get("location");
      if (!location) throw new Error("리다이렉트 위치가 없습니다.");
      current = validateSourceUrl(new URL(location, current).toString());
      continue;
    }
    if (!response.ok) throw new Error(`본문 페이지 응답이 ${response.status}입니다.`);
    const body = extractBody(await readLimited(response));
    return { text: body, chars: body.length, finalUrl: current, source: "본문" };
  }
  throw new Error("리다이렉트가 너무 많습니다.");
}

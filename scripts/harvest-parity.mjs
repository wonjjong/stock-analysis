#!/usr/bin/env node
/**
 * Python 이식의 정답지를 만든다.
 *
 * 이식 동일성(parity)은 동결된 대상에만 증명할 수 있다. 이 스크립트는 지금 동작하는
 * TypeScript 구현을 고정된 입력에 돌려 출력을 JSON으로 남긴다. Python 쪽은 같은 입력에
 * 같은 출력을 내야 한다.
 *
 *   node scripts/harvest-parity.mjs                 # 픽스처 + 합성 케이스만 (네트워크 없음)
 *   node scripts/harvest-parity.mjs --live          # 등록된 소스의 실제 페이지도 수확
 *
 * 산출물: tests/parity/{dates,urls,feed,html,window,analysis,keywords,symbols,robots}.json
 *
 * 왜 이렇게까지 하는가: 모든 추출 경로가 날짜를 못 찾으면 기사를 조용히 버린다. 이식판이
 * 조금이라도 덜 관대하면 예외 없이 기사 수만 줄고 `새 기사 없음`으로 기록된다. 정상처럼
 * 보이므로 몇 주간 모른다. 픽스처 테스트만으로는 이 부류를 잡지 못한다.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { build } from "esbuild";

const OUT_DIR = "tests/parity";
const FIXTURES = "tests/fixtures";
// 픽스처의 08-27 시각이 "오늘"이 되는 고정 시점. 기존 테스트와 같은 값을 쓴다.
const NOW = Date.UTC(2026, 7, 27, 9, 30);
const LIVE = process.argv.includes("--live");

async function load() {
  const entry = `
    export * from "./app/lib/news-crawler.ts";
    export { analyzeNewsLocally } from "./app/lib/news-analysis.ts";
    export { extractKeywords } from "./app/lib/keywords.ts";
    export { matchSymbols, lookupSymbol } from "./app/lib/symbol-dictionary.ts";
    export { extractBody } from "./app/lib/article-body.ts";
  `;
  const bundled = await build({
    stdin: { contents: entry, resolveDir: process.cwd(), loader: "ts" },
    bundle: true, format: "esm", platform: "neutral", write: false, logLevel: "silent",
  });
  const source = bundled.outputFiles[0].text;
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

/** 날짜 판독 — 가장 위험한 이식 지점. Python에 Date.parse 대응물이 없다. */
const DATE_CASES = [
  // 타임존이 명시된 형태 — 그대로 신뢰해야 한다
  "2026-08-27T18:18:07+09:00", "2026-08-27T09:18:07Z", "2026-08-27 18:18:07 KST",
  "Wed, 27 Aug 2026 18:18:07 +0900", "Wed, 27 Aug 2026 09:18:07 GMT",
  // 타임존이 없는 형태 — 한국시간으로 읽어야 한다
  "2026-08-27T18:18", "2026-08-27 18:18:07", "2026.08.27 18:18", "2026/08/27",
  // 연도 없는 형태 — 시각이 함께 있을 때만 인정
  "08-27 18:18", "08.27 18:18", "12-29 21:00", "8-3 9:05",
  // 상대 시각
  "12분 전", "3시간 전", "45 minutes ago", "2 hours ago",
  "오늘 07:30", "오늘", "today 07:30",
  // 한국어 날짜
  "8월 27일", "8월 27일 18시", "8월 27일 18시 30분",
  // 날짜로 오인해선 안 되는 것들 — 전부 null 이어야 한다
  "경기 결과 3-2 완승", "기사 번호 AKR20260827173200001",
  "/image/2026/08/27/thumb.jpg", "조회수 1,234", "1-0", "부산 2-1 승리",
  "12", "12-3", "2026", "", "   ", "댓글 5",
  // 경계값
  "2026-13-45 99:99", "2026-02-30 10:00", "0000-00-00 00:00",
];

/** URL 정규화 — 여기가 틀리면 dedup 인덱스가 조용히 코퍼스를 두 배로 만든다. */
const URL_BASE = "https://news.example.com/news";
const URL_CASES = [
  "/view/AKR20260827173200001", "view/AKR20260827173200001",
  "https://news.example.com/view/1?utm_source=x&utm_medium=y",
  "https://news.example.com/view/1?section=economy&cp=nv",
  "https://news.example.com/view/1?ref=main&from=list&sid=001",
  "https://news.example.com/view/1?keep=yes&utm_campaign=z",
  "https://news.example.com/view/1#comment", "https://news.example.com/view/1?",
  "https://news.example.com:443/view/1", "http://news.example.com:80/view/1",
  "https://news.example.com/a/../b", "https://news.example.com/a/./b",
  "https://news.example.com/%EA%B2%BD%EC%A0%9C/1",
  "https://news.example.com/view/1?q=a+b", "https://news.example.com/view/1?q=a%20b",
  "//news.example.com/view/1", "?page=2", "#top", "",
  "javascript:void(0)", "mailto:a@b.com", "https://다른사이트.kr/기사/1",
];

/** SSRF 가드 — 이식하면서 강화하면 안 된다(동작 차이가 diff를 해석 불가하게 만든다). */
const SOURCE_URL_CASES = [
  "https://news.example.com/latest", "http://news.example.com/latest",
  "https://127.0.0.1/x", "http://localhost/x", "https://10.0.0.1/x",
  "https://192.168.1.1/x", "https://172.16.0.1/x", "https://169.254.169.254/x",
  "https://0.0.0.0/x", "https://[::1]/x", "https://[fd00::1]/x",
  "ftp://news.example.com/x", "file:///etc/passwd", "not-a-url",
  "https://news.example.com:8080/x", "https://user:pass@news.example.com/x",
  "https://1.1.1.1/x", "https://8.8.8.8/x",
];

const ROBOTS_CASES = [
  ["User-agent: *\nDisallow: /", "https://x.com/a"],
  ["User-agent: *\nAllow: /news\nDisallow: /", "https://x.com/news/1"],
  ["User-agent: *\nDisallow: /admin", "https://x.com/news/1"],
  ["User-agent: SignalistResearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /", "https://x.com/a"],
  ["User-agent: *\nDisallow:", "https://x.com/a"],
  ["User-agent: *\nDisallow: /*.pdf$", "https://x.com/a.pdf"],
  ["", "https://x.com/a"],
  ["User-agent: googlebot\nDisallow: /", "https://x.com/a"],
];

const ANALYSIS_CASES = [
  "삼성전자가 3분기 영업이익 컨센서스를 크게 상회하는 실적을 발표했다. 반도체 수요 회복이 이어지고 있다.",
  "HD현대중공업 노조가 파업을 가결했다. 임단협 난항으로 생산 차질이 우려된다.",
  "코스피가 소폭 하락 마감했다. 외국인은 순매도를 이어갔다.",
  "카카오뱅크와 카카오페이가 규제 리스크에 직면했다. 금융당국이 조사에 착수했다.",
  "SK하이닉스는 배당을 확대하고 자사주 매입을 결정했다.",
];

const KEYWORD_CASES = [
  ["임단협 난항 HD현대중 노조, 파업 가결", "노조는 파업 찬반투표에서 재적 대비 66.19%가 찬성했다고 밝혔다."],
  ["삼성전자 3분기 실적 발표", "영업이익이 컨센서스를 상회했다. 반도체 부문이 회복세를 보였다."],
];

const SYMBOL_CASES = [
  "삼성전자와 SK하이닉스가 반도체 업황 회복의 수혜를 볼 전망이다.",
  "카카오뱅크 실적이 개선됐다. 카카오는 별도로 규제 이슈가 있다.",
  "카카오톡으로 공유하기 · 네이버로 공유하기",
  "HD현대중공업 노조가 파업을 가결했다. HD현대는 지주사다.",
  "AAPL과 MSFT가 상승했다. 한편 AAPLE 같은 오타는 종목이 아니다.",
];

const HTML_BODY_CASES = [
  "<div><p>첫 문단입니다.</p><p>두 번째 문단입니다.</p><script>alert(1)</script><p>무단 전재 및 재배포 금지</p></div>",
  "<div>문단 태그가 없는 아주 긴 블록입니다. ".repeat(20) + "</div>",
  "<article><p>짧음</p></article>",
];

const M = await load();
const out = {};
const safe = (fn) => { try { return fn(); } catch (e) { return { __error: String(e?.message ?? e) }; } };

// ── 날짜
out.dates = DATE_CASES.map((input) => ({
  input,
  parseVisibleDate: safe(() => M.parseVisibleDate(input, NOW) ?? null),
}));

// ── dateKst
out.dateKst = [NOW, NOW - 36e5 * 10, NOW + 36e5 * 10, Date.UTC(2026, 11, 31, 15, 30), 0]
  .map((ms) => ({ input: ms, dateKst: safe(() => M.dateKst(ms)) }));

// ── URL 정규화 (parseNewsPage 를 통해 간접 관찰 + validateSourceUrl 직접)
out.sourceUrls = SOURCE_URL_CASES.map((input) => ({
  input,
  validateSourceUrl: safe(() => M.validateSourceUrl(input)),
}));
out.urlsViaAnchors = URL_CASES.map((href) => {
  const html = `<ul><li><a href="${href.replace(/"/g, "&quot;")}">충분히 긴 기사 제목입니다 테스트</a><time datetime="2026-08-27T18:18:00+09:00">18:18</time></li></ul>`;
  return { href, items: safe(() => M.parseNewsPage(html, URL_BASE, NOW).map((i) => i.url)) };
});

// ── 페이지네이션
out.pagination = [
  ["https://news.example.com/news", 1], ["https://news.example.com/news/3", 3],
  ["https://news.example.com/news?cp=5", 5], ["https://news.example.com/news?page=7", 7],
  ["https://news.example.com/news/abc", null],
].map(([url]) => ({ url, pageNumber: safe(() => M.pageNumber(url)) }));

// ── 수집 창
out.window = [
  { hours: 36, offsets: [0, -1, -35, -36, -37, -168, 1, 2, 3] },
  { hours: 6, offsets: [0, -5, -6, -7] },
].flatMap(({ hours, offsets }) =>
  offsets.map((h) => {
    const items = [{ title: "t", url: "u", excerpt: "e", publishedAt: NOW + h * 36e5 }];
    return { hours, offsetHours: h, kept: safe(() => M.selectRecentItems(items, NOW, hours).length) };
  }),
);
out.clampWindowHours = [0, -5, 3, 6, 36, 168, 999, 1.9, NaN, Infinity]
  .map((h) => ({ input: Number.isFinite(h) ? h : String(h), clamped: safe(() => M.clampWindowHours(h)) }));

// ── 다음 실행 시각
out.nextRunAt = [0, 6, 9, 15, 23, -1, 24, 6.7]
  .map((hour) => ({ hour, now: NOW, nextRunAt: safe(() => M.nextRunAt(hour, NOW)) }));

// ── robots
out.robots = ROBOTS_CASES.map(([text, url]) => ({
  text, url, allowed: safe(() => M.robotsAllows(text, new URL(url))),
}));

// ── 규칙 기반 분석
out.analysis = ANALYSIS_CASES.map((text) => ({
  text, result: safe(() => M.analyzeNewsLocally(text, "MARKET", "시장 전체")),
}));

// ── 키워드
out.keywords = KEYWORD_CASES.map(([title, body]) => ({
  title, body, keywords: safe(() => M.extractKeywords(title, body)),
}));

// ── 종목 매칭
out.symbols = SYMBOL_CASES.map((text) => ({
  text, matches: safe(() => M.matchSymbols("", text)),
}));

// ── 본문 추출
out.body = HTML_BODY_CASES.map((html) => ({
  htmlLength: html.length, body: safe(() => M.extractBody(html)),
}));

// ── 픽스처 (RSS·HTML 목록)
if (existsSync(`${FIXTURES}/news-feed.xml`)) {
  const xml = await readFile(`${FIXTURES}/news-feed.xml`, "utf8");
  out.feedFixture = safe(() => M.parseFeed(xml, "https://news.example.com/rss"));
}
if (existsSync(`${FIXTURES}/news-list.html`)) {
  const html = await readFile(`${FIXTURES}/news-list.html`, "utf8");
  out.htmlFixture = {
    items: safe(() => M.parseNewsPage(html, URL_BASE, NOW)),
    nextPage: safe(() => M.findNextPageUrl(html, URL_BASE)),
  };
}

// ── 라이브 페이지 (--live)
if (LIVE) {
  const { getD1, getPool } = await import(`${process.cwd()}/node_modules/.cache/signalist/scheduler-bundle.mjs`)
    .catch(() => ({ getD1: null, getPool: null }));
  if (getD1) {
    const rows = await getD1().prepare("SELECT id, name, url, resolved_url FROM news_sources WHERE is_active = true").all();
    out.liveSources = [];
    for (const s of rows.results) {
      const target = s.resolved_url ?? s.url;
      try {
        const response = await fetch(target, { headers: { "user-agent": "SignalistResearchBot/1.1 (parity harvest)" }, signal: AbortSignal.timeout(20_000) });
        const text = await response.text();
        const isFeed = /^\s*<\?xml|<rss|<feed/i.test(text);
        out.liveSources.push({
          id: s.id, name: s.name, url: target, contentType: response.headers.get("content-type"),
          bytes: text.length, kind: isFeed ? "feed" : "html",
          items: safe(() => (isFeed ? M.parseFeed(text, target) : M.parseNewsPage(text, target, NOW))),
        });
        await writeFile(`${OUT_DIR}/pages/${s.id}.raw`, text, "utf8");
      } catch (reason) {
        out.liveSources.push({ id: s.id, name: s.name, url: target, error: String(reason?.message ?? reason) });
      }
    }
    await getPool?.().end().catch(() => {});
  } else {
    out.liveSources = { __error: "스케줄러 번들이 없습니다. `npm run scheduler:once` 를 한 번 실행하세요." };
  }
}

await mkdir(`${OUT_DIR}/pages`, { recursive: true });
const meta = { now: NOW, nowIso: new Date(NOW).toISOString(), live: LIVE, node: process.version };
await writeFile(`${OUT_DIR}/expected.json`, JSON.stringify({ meta, ...out }, null, 2) + "\n", "utf8");

const counts = Object.entries(out).map(([k, v]) => `${k}=${Array.isArray(v) ? v.length : 1}`);
console.log(`${OUT_DIR}/expected.json 기록`);
console.log(counts.join(" "));

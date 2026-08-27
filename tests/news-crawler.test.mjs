// Workers run in UTC; pin the tests there so timezone-dependent parsing cannot
// pass locally and fail in production.
process.env.TZ = "UTC";

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { build } from "esbuild";

// The crawler is TypeScript that the worker bundles at build time; compile it
// in-memory so these tests exercise the same source the worker ships.
const bundled = await build({
  entryPoints: [new URL("../app/lib/news-crawler.ts", import.meta.url).pathname],
  bundle: true,
  format: "esm",
  platform: "neutral",
  write: false,
});
const {
  clampWindowHours, dateKst, findNextPageUrl, nextRunAt, pageNumber, parseFeed, parseNewsPage, parseVisibleDate,
  robotsAllows, selectRecentItems, validateSourceUrl,
} = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`);

const fixture = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8");
const LIST_URL = "https://news.example.com/news";
// 2026-08-27 18:30 KST, so the fixture's 08-27 stamps are "today".
const NOW = Date.UTC(2026, 7, 27, 9, 30);
const kstClock = (time) => new Date(time + 9 * 60 * 60 * 1000).toISOString().slice(0, 16);

test("긴 리드 문단 뒤의 발행시각 태그를 읽는다", () => {
  const items = parseNewsPage(fixture("news-list.html"), LIST_URL, NOW);
  const lead = items.find((item) => item.title.includes("여당 연찬회"));
  assert.ok(lead, "리드 본문이 긴 기사도 수집돼야 한다");
  assert.equal(kstClock(lead.publishedAt), "2026-08-27T18:18");
});

test("잘린 이미지 태그의 경로를 발행일로 오인하지 않는다", () => {
  const items = parseNewsPage(fixture("news-list.html"), LIST_URL, NOW);
  for (const item of items) {
    assert.equal(new Date(item.publishedAt).getUTCFullYear(), 2026, `${item.title} 의 발행연도가 어긋났다`);
  }
});

test("목록 문맥의 날짜만 인정하고 날짜 없는 항목은 버린다", () => {
  const items = parseNewsPage(fixture("news-list.html"), LIST_URL, NOW);
  assert.equal(items.length, 3);
  assert.ok(!items.some((item) => item.title.includes("날짜 표시가 없는")));
  const yesterday = items.find((item) => item.title.includes("통화안정증권"));
  assert.equal(dateKst(yesterday.publishedAt), "2026-08-26");
});

test("섹션·추적 쿼리를 제거해 같은 기사를 한 번만 남긴다", () => {
  const items = parseNewsPage(fixture("news-list.html"), LIST_URL, NOW);
  const urls = items.map((item) => item.url);
  assert.equal(new Set(urls).size, urls.length);
  assert.ok(urls.includes("https://news.example.com/view/AKR20260827173200001"));
  assert.ok(!urls.some((url) => url.includes("section=")));
});

test("RSS 피드의 제목·링크·발행시각을 판독한다", () => {
  const items = parseFeed(fixture("news-feed.xml"), "https://news.example.com/rss/news.xml");
  assert.equal(items.length, 2);
  assert.equal(items[0].title, "여당 연찬회에서 나온 단일 대오 요구와 지도부 책임론");
  assert.equal(items[0].url, "https://news.example.com/view/AKR20260827173200001");
  assert.equal(kstClock(items[0].publishedAt), "2026-08-27T18:18");
});

test("다음 페이지 링크를 찾고 페이지 번호를 읽는다", () => {
  assert.equal(findNextPageUrl(fixture("news-list.html"), LIST_URL), "https://news.example.com/news/2");
  assert.equal(findNextPageUrl(fixture("news-list.html"), "https://news.example.com/news/2"), "https://news.example.com/news/3");
  assert.equal(findNextPageUrl(fixture("news-list.html"), "https://news.example.com/news/4"), "");
  assert.equal(pageNumber("https://news.example.com/news"), 1);
  assert.equal(pageNumber("https://news.example.com/news/3"), 3);
  assert.equal(pageNumber("https://news.example.com/news?cp=5"), 5);
});

test("rel=next 링크를 우선 사용한다", () => {
  const html = '<link rel="next" href="/latest?page=2"><a href="/latest/9">2</a>';
  assert.equal(findNextPageUrl(html, "https://news.example.com/latest"), "https://news.example.com/latest?page=2");
});

test("연-월-일 없는 숫자는 시각이 함께 있을 때만 날짜로 인정한다", () => {
  assert.equal(parseVisibleDate("08-27 18:18", NOW), Date.UTC(2026, 7, 27, 9, 18));
  assert.equal(parseVisibleDate("경기 결과 3-2 완승", NOW), null);
  assert.equal(parseVisibleDate("기사 번호 AKR20260827173200001", NOW), null);
  assert.equal(parseVisibleDate("2026-08-27T18:18:07+09:00", NOW), Date.UTC(2026, 7, 27, 9, 18, 7));
  assert.equal(parseVisibleDate("12분 전", NOW), NOW - 12 * 60_000);
  assert.equal(parseVisibleDate("오늘 07:30", NOW), Date.UTC(2026, 7, 26, 22, 30));
});

test("12월 목록을 1월에 읽어도 연도를 되돌린다", () => {
  const january = Date.UTC(2027, 0, 2, 1, 0);
  assert.equal(dateKst(parseVisibleDate("12-29 21:00", january)), "2026-12-29");
});

test("robots.txt 규칙과 내부망 주소를 차단한다", () => {
  const rules = "User-agent: *\nAllow:/\nDisallow: /search/\nDisallow: /*?*cp=";
  assert.equal(robotsAllows(rules, new URL("https://news.example.com/news")), true);
  assert.equal(robotsAllows(rules, new URL("https://news.example.com/search/?q=1")), false);
  assert.equal(robotsAllows(rules, new URL("https://news.example.com/news?cp=2")), false);
  assert.throws(() => validateSourceUrl("http://127.0.0.1/news"));
  assert.throws(() => validateSourceUrl("http://192.168.0.5/news"));
  assert.equal(validateSourceUrl("https://news.example.com/news#top"), "https://news.example.com/news");
});

test("다음 실행 시각은 항상 미래의 지정된 한국시간이다", () => {
  const next = nextRunAt(6, NOW);
  assert.ok(next > NOW);
  assert.equal(kstClock(next), "2026-08-28T06:00");
  assert.equal(kstClock(nextRunAt(23, NOW)), "2026-08-27T23:00");
});

test("한국시간 날짜가 아니라 발행 경과 시간으로 거른다", () => {
  const hours = (value) => ({ title: `${value}시간 전 기사`, url: `https://news.example.com/${value}`, excerpt: "", publishedAt: NOW - value * 3_600_000 });
  const items = [hours(1), hours(20), hours(30), hours(47), { title: "날짜 없음", url: "https://news.example.com/x", excerpt: "", publishedAt: null }];

  const day = selectRecentItems(items, NOW, 24).map((item) => item.url);
  assert.deepEqual(day, ["https://news.example.com/1", "https://news.example.com/20"]);

  // 36시간 창은 하루 한 번 실행과 12시간 겹치므로 사이에 빈 구간이 없다.
  const wide = selectRecentItems(items, NOW, 36).map((item) => item.url);
  assert.deepEqual(wide, ["https://news.example.com/1", "https://news.example.com/20", "https://news.example.com/30"]);
});

test("어제 한국시간에 나온 해외 기사도 창 안이면 남긴다", () => {
  // 미국 동부 27일 07:00 = 한국시간 27일 20:00, 그러나 26일 오후 ET 발행분은 한국시간 27일 새벽이다.
  const yesterdayKst = Date.UTC(2026, 7, 26, 20, 0);
  assert.equal(dateKst(yesterdayKst), "2026-08-27");
  const beforeThat = Date.UTC(2026, 7, 26, 8, 0);
  assert.equal(dateKst(beforeThat), "2026-08-26");
  const kept = selectRecentItems([{ title: "US wire", url: "https://news.example.com/us", excerpt: "", publishedAt: beforeThat }], NOW, 36);
  assert.equal(kept.length, 1, "한국시간 어제 발행분도 36시간 창 안에서는 유지돼야 한다");
});

test("미래로 찍힌 발행시각은 시계 오차 범위까지만 허용한다", () => {
  const skewed = (ms) => [{ title: "미래", url: "https://news.example.com/f", excerpt: "", publishedAt: NOW + ms }];
  assert.equal(selectRecentItems(skewed(30 * 60_000), NOW, 36).length, 1);
  assert.equal(selectRecentItems(skewed(6 * 3_600_000), NOW, 36).length, 0);
});

test("수집 기간 설정은 허용 범위로 제한한다", () => {
  assert.equal(clampWindowHours(48), 48);
  assert.equal(clampWindowHours(1), 6);
  assert.equal(clampWindowHours(1000), 168);
  assert.equal(clampWindowHours(Number.NaN), 36);
});

test("타임존 없는 피드 시각을 실행 환경이 아니라 한국시간으로 읽는다", () => {
  const feed = `<rss><channel><item><title>한은, 9월 통안채 7조 발행</title>
    <link>https://news.example.com/view/1</link><pubDate>2026-08-27 19:28:10</pubDate></item></channel></rss>`;
  const [item] = parseFeed(feed, "https://news.example.com/rss");
  assert.equal(item.publishedAt, Date.UTC(2026, 7, 27, 10, 28, 10));
  assert.equal(dateKst(item.publishedAt), "2026-08-27");
  // UTC로 읽혔다면 9시간 미래가 되어 수집 창에서 탈락한다.
  assert.equal(selectRecentItems([item], NOW + 3_600_000, 36).length, 1);
});

test("타임존이 붙은 피드 시각은 그대로 신뢰한다", () => {
  const feed = (stamp) => `<rss><channel><item><title>Nvidia forecasts sales growth</title>
    <link>https://news.example.com/view/2</link><pubDate>${stamp}</pubDate></item></channel></rss>`;
  assert.equal(parseFeed(feed("Thu, 27 Aug 2026 18:18:07 +0900"), "https://x")[0].publishedAt, Date.UTC(2026, 7, 27, 9, 18, 7));
  assert.equal(parseFeed(feed("Thu, 27 Aug 2026 09:18:07 GMT"), "https://x")[0].publishedAt, Date.UTC(2026, 7, 27, 9, 18, 7));
  assert.equal(parseFeed(feed("2026-08-27T09:18:07Z"), "https://x")[0].publishedAt, Date.UTC(2026, 7, 27, 9, 18, 7));
});

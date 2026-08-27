import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }), { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } }, { waitUntil() {}, passThroughOnException() {} });
}

test("메인 리서치 대시보드를 서버 렌더링한다", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Signalist/);
  assert.match(html, /오늘의 추천 종목/);
  assert.match(html, /VIX/);
  assert.match(html, /삼성전자/);
  assert.doesNotMatch(html, /react-loading-skeleton|Building your site/);
});

test("종목 상세와 포트폴리오를 서버 렌더링한다", async () => {
  const [detail, portfolio] = await Promise.all([render("/stock/005930"), render("/portfolio")]);
  assert.equal(detail.status, 200);
  assert.equal(portfolio.status, 200);
  assert.match(await detail.text(), /SENIOR ANALYST REPORT|AI 재분석/);
  assert.match(await portfolio.text(), /보유종목/);
});

test("뉴스 분석실을 서버 렌더링한다", async () => {
  const response = await render("/news");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /NEWS ANALYSIS LAB/);
  assert.match(html, /뉴스 분석하기/);
  assert.match(html, /추천점수 조정/);
});

test("뉴스 자동 수집 관리 화면을 서버 렌더링한다", async () => {
  const response = await render("/news/sources");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /DAILY NEWS SCRAPER/);
  assert.match(html, /등록하고 오늘 기사 수집/);
  assert.match(html, /저장 기사/);
});

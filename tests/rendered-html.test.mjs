import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import test, { after, before } from "node:test";

/**
 * 예전에는 `dist/server/index.js`의 Cloudflare Worker export를 직접 불러
 * `worker.fetch(request, env, ctx)`를 호출했다. Worker를 떠난 뒤로는 그 export가
 * 없으므로, 실제로 서비스되는 방식 그대로 `next start`를 띄우고 HTTP로 확인한다.
 */

const PORT = Number(process.env.SSR_TEST_PORT ?? 3199);
const BASE = `http://127.0.0.1:${PORT}`;
const BOOT_TIMEOUT_MS = 60_000;

let server;

async function waitForServer() {
  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`서버가 조기 종료했습니다 (code ${server.exitCode})`);
    try {
      const response = await fetch(BASE, { headers: { accept: "text/html" } });
      if (response.status < 500) return;
    } catch {
      // 아직 리스닝 전이다.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${BOOT_TIMEOUT_MS}ms 안에 서버가 뜨지 않았습니다.`);
}

before(async () => {
  server = spawn("node", ["node_modules/.bin/next", "start", "--port", String(PORT)], {
    stdio: ["ignore", "pipe", "pipe"],
    // DB가 없어도 렌더링은 되어야 한다(뉴스 화면은 클라이언트에서 데이터를 받는다).
    env: { ...process.env, PORT: String(PORT) },
  });
  server.stderr.on("data", (chunk) => {
    const text = String(chunk);
    if (/error/i.test(text)) process.stderr.write(`[next] ${text}`);
  });
  await waitForServer();
});

after(async () => {
  if (!server || server.exitCode !== null) return;
  server.kill("SIGTERM");
  await new Promise((resolve) => {
    const timer = setTimeout(() => { server.kill("SIGKILL"); resolve(); }, 5_000);
    server.once("exit", () => { clearTimeout(timer); resolve(); });
  });
});

async function render(path = "/") {
  return fetch(`${BASE}${path}`, { headers: { accept: "text/html" } });
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

test("뉴스 기사 아카이브 화면을 서버 렌더링한다", async () => {
  const response = await render("/news/archive");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /COLLECTED ARTICLE ARCHIVE/);
  assert.match(html, /필터 초기화/);
  assert.match(html, /전체 소스/);
});

test("AI 공급자 설정 화면을 서버 렌더링한다", async () => {
  const response = await render("/news/providers");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /FREE TIER FAILOVER/);
  assert.match(html, /공급자 등록/);
  assert.match(html, /우선순위/);
});

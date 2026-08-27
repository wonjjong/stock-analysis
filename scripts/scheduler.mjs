#!/usr/bin/env node
/**
 * Cloudflare Worker의 `scheduled` 핸들러를 대체한다.
 *
 * Worker에는 상시 프로세스가 없어 플랫폼이 매시 정각에 깨워 주었다. 평범한 Node에서는
 * 프로세스가 계속 살아 있으므로 직접 주기를 돈다. 소스별 실행 시각은 예전과 같이
 * `news_sources.next_crawl_at`이 관리하므로 여기서는 기한이 된 소스를 자주 확인만 한다.
 *
 *   npm run scheduler                  # 기본 60초 주기
 *   TICK_SECONDS=300 npm run scheduler
 *   npm run scheduler:once             # 한 번만 실행하고 종료 (외부 cron/CI용)
 *
 * app/ 소스는 확장자 없는 번들러 스타일 import를 쓰므로 Node가 직접 해석하지 못한다.
 * tests/news-crawler.test.mjs와 같은 방식으로 esbuild로 인메모리 번들해 불러온다.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { build } from "esbuild";

const TICK_MS = Math.max(10, Number(process.env.TICK_SECONDS ?? 60)) * 1000;
const INSIGHT_BATCH = Math.max(1, Number(process.env.INSIGHT_BATCH ?? 20));
const ONCE = process.argv.includes("--once");

function log(message, extra) {
  const stamp = new Date().toISOString();
  if (extra === undefined) console.log(`[${stamp}] ${message}`);
  else console.log(`[${stamp}] ${message}`, extra);
}

/**
 * 크롤러·인사이트·DB를 한 진입점으로 묶어 번들한 뒤 불러온다.
 *
 * 번들은 프로젝트 안 파일로 쓴다. data: URL로 불러오면 해석 기준점이 없어
 * `pg`, `drizzle-orm` 같은 bare specifier를 찾지 못한다.
 */
async function load() {
  const entry = `
    export { crawlDueSources } from "./app/lib/news-crawler.ts";
    export { processPendingInsights } from "./app/lib/news-insights.ts";
    export { getD1, getPool } from "./db/index.ts";
  `;
  const outfile = `${process.cwd()}/node_modules/.cache/signalist/scheduler-bundle.mjs`;
  const bundled = await build({
    stdin: { contents: entry, resolveDir: process.cwd(), loader: "ts" },
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node22",
    // pg는 Node 소켓을 쓰고 drizzle은 그 위에 얹히므로 번들에 넣지 않는다.
    external: ["pg", "pg-native", "drizzle-orm"],
    write: false,
    logLevel: "silent",
  });
  await mkdir(new URL(".", pathToFileURL(outfile)), { recursive: true });
  await writeFile(outfile, bundled.outputFiles[0].text, "utf8");
  return import(`${pathToFileURL(outfile).href}?t=${Date.now()}`);
}

/** Worker의 scheduled()와 같은 순서다: 수집이 끝난 뒤 밀린 본문 분석을 한 배치 소화한다. */
async function tick({ crawlDueSources, processPendingInsights, getD1 }) {
  const db = getD1();
  const crawled = await crawlDueSources(db);
  if (crawled.length) log(`수집 ${crawled.length}건`, crawled);

  const insights = await processPendingInsights(db, INSIGHT_BATCH);
  if (insights.picked) log("본문 분석", insights);

  if (!crawled.length && !insights.picked) log("기한이 된 소스와 대기 기사가 없습니다.");
  return { crawled: crawled.length, insights };
}

const modules = await load();
let running = false;
let stopping = false;

async function safeTick() {
  // 한 tick이 길어지면 다음 tick을 건너뛴다. Worker에서는 플랫폼이 보장해 주던 성질이다.
  if (running) return log("이전 tick이 아직 진행 중 — 건너뜀");
  running = true;
  try {
    await tick(modules);
  } catch (reason) {
    log(`tick 실패: ${reason instanceof Error ? reason.message : reason}`);
    if (ONCE) process.exitCode = 1;
  } finally {
    running = false;
  }
}

await safeTick();

if (ONCE) {
  await modules.getPool().end().catch(() => {});
} else {
  log(`스케줄러 시작 — ${TICK_MS / 1000}초 주기`);
  const timer = setInterval(safeTick, TICK_MS);
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, async () => {
      if (stopping) return;
      stopping = true;
      log(`${signal} 수신 — 종료`);
      clearInterval(timer);
      await modules.getPool().end().catch(() => {});
      process.exit(0);
    });
  }
}

process.env.TZ = "UTC";

import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";

// 본문 추출·종목 사전·키워드는 워커가 번들하는 소스 그대로 검증한다.
async function load(path) {
  const bundled = await build({
    entryPoints: [new URL(path, import.meta.url).pathname],
    bundle: true, format: "esm", platform: "neutral", write: false,
  });
  return import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`);
}

const { extractBody } = await load("../app/lib/article-body.ts");
const { matchSymbols, lookupSymbol } = await load("../app/lib/symbol-dictionary.ts");
const { extractKeywords } = await load("../app/lib/keywords.ts");
const { ruleInsight } = await load("../app/lib/news-insights.ts");

test("문단 태그에서 본문만 모으고 스크립트와 저작권 문구는 버린다", () => {
  const html = `<html><body><nav>메뉴 모음입니다 여기는 본문이 아닙니다</nav>
    <script>var tracking = "무시해야 하는 스크립트 본문입니다";</script>
    <article><p>삼성전자가 27일 반도체 부문 실적이 개선됐다고 발표했습니다.</p>
    <p>회사는 고대역폭 메모리 공급을 늘리겠다고 설명했습니다.</p>
    <p>저작권자(c) 연합뉴스, 무단 전재-재배포 금지</p></article></body></html>`;
  const body = extractBody(html);
  assert.match(body, /삼성전자가 27일 반도체/);
  assert.match(body, /고대역폭 메모리/);
  assert.doesNotMatch(body, /tracking|무단 전재/);
});

test("문단이 없으면 가장 긴 블록으로 본문을 대체한다", () => {
  const html = `<div>짧다</div><div>${"기사 본문이 문단 태그 없이 들어 있는 경우입니다. ".repeat(4)}</div>`;
  assert.match(extractBody(html), /문단 태그 없이/);
});

test("긴 종목명을 먼저 세어 카카오뱅크가 카카오로 중복 집계되지 않는다", () => {
  const matches = matchSymbols("카카오뱅크 실적 발표", "카카오뱅크는 순이익이 늘었다고 밝혔다.");
  assert.deepEqual(matches.map((item) => item.symbol), ["323410"]);
});

test("공유 버튼의 카카오톡 문구는 종목으로 세지 않는다", () => {
  const matches = matchSymbols("인권위 직권조사 개시", "군 사망 사건을 조사한다. 제보는 카카오톡 okjebo");
  assert.deepEqual(matches, []);
});

test("제목에 나온 종목이 본문에만 나온 종목보다 관련도가 높다", () => {
  const matches = matchSymbols("삼성전자 HBM 증설", "삼성전자는 SK하이닉스와 경쟁한다.");
  assert.equal(matches[0].symbol, "005930");
  assert.ok(matches[0].relevance > matches[1].relevance);
});

test("영문 티커는 단어 경계를 지켜 오탐을 막는다", () => {
  assert.deepEqual(matchSymbols("alarm systems", "The alarm market grows."), []);
  assert.equal(matchSymbols("ARM 실적", "ARM Holdings reported revenue.")[0].symbol, "ARM");
});

test("종목을 코드·이름·별칭으로 찾는다", () => {
  assert.equal(lookupSymbol("005930").name, "삼성전자");
  assert.equal(lookupSymbol("엔비디아").symbol, "NVDA");
  assert.equal(lookupSymbol("없는회사"), null);
});

test("조사를 떼고 제목 단어에 가중치를 줘 키워드를 뽑는다", () => {
  const keywords = extractKeywords("반도체 수출 증가", "반도체 수출이 늘었다. 반도체 업황이 좋아졌다고 기자가 밝혔다.");
  assert.ok(keywords.includes("반도체"));
  assert.ok(keywords.includes("수출"));
  assert.ok(!keywords.includes("기자"));
});

test("규칙 기반 인사이트가 요약·키워드·업종을 채운다", () => {
  const insight = ruleInsight("삼성전자 영업이익 증가", "삼성전자는 반도체 실적 개선으로 영업이익이 늘었다고 27일 발표했습니다. 회사는 매출도 확대됐다고 설명했습니다.");
  assert.equal(insight.engine, "규칙 기반");
  assert.equal(insight.sentiment, "긍정");
  assert.ok(insight.summary.length > 10);
  assert.ok(insight.keywords.length > 0);
  assert.deepEqual(insight.sectors, ["반도체"]);
});

const { llmConfig, llmJson } = await load("../app/lib/llm.ts");

test("OpenAI 호환 엔드포인트를 호출하고 코드펜스 안의 JSON도 읽는다", async () => {
  const { createServer } = await import("node:http");
  const requests = [];
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      requests.push({ url: request.url, auth: request.headers.authorization, body: JSON.parse(body) });
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content: "```json\n{\"summary\":\"요약\",\"sentiment\":\"긍정\"}\n```" } }] }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;

  process.env.SIGNALIST_LLM_API_KEY = "test-key";
  process.env.SIGNALIST_LLM_BASE_URL = `http://127.0.0.1:${port}/v1`;
  process.env.SIGNALIST_LLM_MODEL = "test-model";
  try {
    const config = llmConfig();
    assert.equal(config.model, "test-model");
    const parsed = await llmJson(config, "시스템", "사용자");
    assert.deepEqual(parsed, { summary: "요약", sentiment: "긍정" });
    assert.equal(requests[0].url, "/v1/chat/completions");
    assert.equal(requests[0].auth, "Bearer test-key");
    assert.equal(requests[0].body.model, "test-model");
    assert.equal(requests[0].body.response_format.type, "json_object");
  } finally {
    delete process.env.SIGNALIST_LLM_API_KEY;
    delete process.env.SIGNALIST_LLM_BASE_URL;
    delete process.env.SIGNALIST_LLM_MODEL;
    server.close();
  }
});

test("키가 없으면 LLM 설정을 만들지 않는다", () => {
  const saved = { key: process.env.SIGNALIST_LLM_API_KEY, legacy: process.env.SIGNALIST_OPENAI_API_KEY };
  delete process.env.SIGNALIST_LLM_API_KEY;
  delete process.env.SIGNALIST_OPENAI_API_KEY;
  try { assert.equal(llmConfig(), null); }
  finally {
    if (saved.key) process.env.SIGNALIST_LLM_API_KEY = saved.key;
    if (saved.legacy) process.env.SIGNALIST_OPENAI_API_KEY = saved.legacy;
  }
});

const { classifyFailure, cooldownUntil, availableProviders, llmJsonWithFailover } = await load("../app/lib/llm.ts");

// llm.ts가 쓰는 표면만 흉내 낸다: prepare().bind().all() / .run()
function fakeDb(rows) {
  const updates = [];
  return {
    updates,
    prepare(sql) {
      return {
        bind(...params) { return this._with(params); },
        _with(params) {
          return {
            all: async () => ({ success: true, results: rows, meta: {} }),
            run: async () => { updates.push({ sql: sql.replace(/\s+/g, " ").trim(), params }); return { success: true, results: [], meta: { changes: 1 } }; },
            first: async () => rows[0] ?? null,
          };
        },
        all: async () => ({ success: true, results: rows, meta: {} }),
        run: async () => ({ success: true, results: [], meta: { changes: 0 } }),
        first: async () => rows[0] ?? null,
      };
    },
    batch: async () => [],
  };
}

const provider = (over) => ({
  id: 1, name: "P", base_url: "http://127.0.0.1:1/v1", model: "m", api_key: "k", priority: 10,
  is_active: true, daily_limit: 0, used_today: 0, usage_date_kst: null, cooldown_until: null,
  last_status: "대기", last_error: null, last_used_at: null, success_count: 0, failure_count: 0, ...over,
});

test("HTTP 상태를 실패 종류로 나눈다", () => {
  assert.equal(classifyFailure(429, ""), "한도 초과");
  assert.equal(classifyFailure(402, ""), "한도 초과");
  assert.equal(classifyFailure(400, "You exceeded your quota"), "한도 초과");
  assert.equal(classifyFailure(401, ""), "인증 오류");
  assert.equal(classifyFailure(503, ""), "일시 오류");
  assert.equal(classifyFailure(400, "bad model name"), "요청 오류");
});

test("한도 초과 휴식은 한국시간 자정을 넘기지 않는다", () => {
  // 한국시간 23:30 → 30분 뒤 자정이 한 시간보다 가깝다.
  const late = Date.UTC(2026, 7, 27, 14, 30);
  assert.equal(cooldownUntil("한도 초과", late), Date.UTC(2026, 7, 27, 15, 0));
  const noon = Date.UTC(2026, 7, 27, 3, 0);
  assert.equal(cooldownUntil("한도 초과", noon), noon + 60 * 60 * 1000);
  assert.ok(cooldownUntil("인증 오류", noon) > cooldownUntil("일시 오류", noon));
});

test("휴식 중이거나 일일 한도를 채운 공급자는 후보에서 뺀다", async () => {
  const now = Date.UTC(2026, 7, 27, 3, 0);
  const today = new Date(now + 9 * 3600 * 1000).toISOString().slice(0, 10);
  const rows = [
    provider({ id: 1, name: "휴식중", cooldown_until: now + 60_000 }),
    provider({ id: 2, name: "한도소진", daily_limit: 5, used_today: 5, usage_date_kst: today }),
    provider({ id: 3, name: "어제한도", daily_limit: 5, used_today: 5, usage_date_kst: "2026-08-26" }),
    provider({ id: 4, name: "정상" }),
  ];
  const names = (await availableProviders(fakeDb(rows), now)).map((row) => row.name);
  assert.deepEqual(names, ["어제한도", "정상"]);
});

test("앞 공급자가 막히면 다음 공급자로 넘어가고 실패를 기록한다", async () => {
  const { createServer } = await import("node:http");
  const servers = [];
  const listen = (handler) => new Promise((resolve) => {
    const server = createServer(handler);
    servers.push(server);
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });

  const overPort = await listen((_q, res) => { res.writeHead(429); res.end('{"error":"rate limit"}'); });
  const authPort = await listen((_q, res) => { res.writeHead(401); res.end('{"error":"bad key"}'); });
  const okPort = await listen((_q, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ choices: [{ message: { content: '{"summary":"됐다"}' } }] }));
  });

  try {
    const rows = [
      provider({ id: 1, name: "1순위", priority: 1, base_url: `http://127.0.0.1:${overPort}/v1` }),
      provider({ id: 2, name: "2순위", priority: 2, base_url: `http://127.0.0.1:${authPort}/v1` }),
      provider({ id: 3, name: "3순위", priority: 3, base_url: `http://127.0.0.1:${okPort}/v1` }),
    ];
    const db = fakeDb(rows);
    const result = await llmJsonWithFailover(db, "시스템", "사용자", Date.now());
    assert.deepEqual(result.parsed, { summary: "됐다" });
    assert.equal(result.provider.name, "3순위");
    assert.deepEqual(result.attempts.map((item) => `${item.name}:${item.kind}`), ["1순위:한도 초과", "2순위:인증 오류", "3순위:성공"]);
    // 실패 두 건과 성공 한 건이 각각 DB에 기록된다.
    assert.equal(db.updates.length, 3);
    assert.ok(db.updates[0].sql.includes("cooldown_until = ?"));
    assert.ok(db.updates[2].sql.includes("success_count = success_count + 1"));
  } finally {
    for (const server of servers) server.close();
  }
});

test("모든 공급자가 막히면 결과 없이 시도 내역만 돌려준다", async () => {
  const { createServer } = await import("node:http");
  const server = createServer((_q, res) => { res.writeHead(429); res.end("{}"); });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const rows = [provider({ id: 1, name: "유일", base_url: `http://127.0.0.1:${server.address().port}/v1` })];
    const result = await llmJsonWithFailover(fakeDb(rows), "시스템", "사용자", Date.now());
    assert.equal(result.parsed, null);
    assert.equal(result.provider, null);
    assert.deepEqual(result.attempts.map((item) => item.kind), ["한도 초과"]);
  } finally { server.close(); }
});

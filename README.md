# Signalist

재무제표, 가격·수급, 뉴스와 거시경제를 함께 해석하는 AI 주식 리서치 워크스페이스입니다.

**현재 뉴스 파이프라인과 단일 미국 종목 AI 분석실이 동작합니다.** 뉴스 사이트를 등록하면 주기적으로 기사를
수집하고, 본문을 읽어 요약·키워드·감성·영향 업종을 뽑고, 종목 사전으로 언급된 종목을 연결합니다.
시장 전체 팩터 랭킹·백테스트는 아직 없습니다.

- `/` — 파이프라인 상태 한 화면: 소스, 분석 큐, 공급자, 최근 실행, 많이 언급된 종목
- `/news/sources` — 뉴스 사이트 등록, 수집 시각·목록 페이지 수·수집 창 관리
- `/news/archive` — 수집한 기사를 기간·소스·종목·감성으로 검색. 행을 펼치면 요약·키워드·태깅 종목·시장 관점·근거
- `/news/providers` — AI 공급자 등록, 우선순위·일일 한도·쿨다운
- `/news/lab` — 기사를 붙여넣어 규칙 엔진과 AI가 무엇을 뽑는지 확인 (저장하지 않음)
- `/research/lab` — 미국 티커의 시세·재무·뉴스를 조회해 등록한 AI 공급자로 분석 (저장하지 않음)
- `/admin/` — 운영 조회: 크롤 실패 원인, 큐 적체, 공급자 사용량

---

## 목차

- [실행](#실행)
- [아키텍처](#아키텍처)
- [코드 구조](#코드-구조) ← 어디에 무엇이 있나
- [데이터베이스](#데이터베이스)
- [뉴스 수집](#뉴스-수집)
- [본문 기반 분석 파이프라인](#본문-기반-분석-파이프라인)
- [AI 공급자 우선순위와 폴백](#ai-공급자-우선순위와-폴백)
- [TypeScript 에서 Python 으로](#typescript-에서-python-으로)
- [테스트](#테스트)
- [주의할 함정](#주의할-함정)
- [추천 모델 교정 내용](#추천-모델-교정-내용)
- [데이터 수집 원칙](#데이터-수집-원칙)
- [Point-in-time 저장 설계](#point-in-time-저장-설계)
- [앞으로](#앞으로)

---

## 실행

```bash
docker compose up -d                      # PostgreSQL 16 (호스트 포트 55432)
cd backend
python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp ../.env.example ../.env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver      # http://localhost:8000
.venv/bin/python manage.py run_scheduler  # 별 터미널 — 주기 수집·본문 분석
```

`DATABASE_URL`은 `.env`에 둡니다. 기본값은 compose가 노출하는
`postgresql://postgres:postgres@localhost:55432/signalist`입니다.

| 명령 | 내용 |
|---|---|
| `manage.py runserver` | 개발 서버 |
| `manage.py run_scheduler [--interval N] [--batch N] [--once]` | 주기 수집 + 본문 분석 |
| `manage.py crawl_news [--source N] [--limit N]` | 기한이 된 소스 수집 |
| `manage.py analyze_news [--limit N] [--stats]` | 본문 분석 / 큐 현황 |
| `manage.py migrate` · `makemigrations` | 스키마 |
| `manage.py createsuperuser` | Admin 계정 |
| `.venv/bin/python -m pytest` | 테스트 96개 |
| `.venv/bin/ruff check .` | 린트 |

### 환경변수

| 변수 | 필수 | 내용 |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL 접속 문자열 |
| `DATABASE_POOL_MAX` | | 커넥션 풀 상한 (기본 10) |
| `DJANGO_SECRET_KEY` | 배포시 ✅ | prod 설정에서 필수 |
| `DJANGO_ALLOWED_HOSTS` | 배포시 | 콤마 구분 |
| `SIGNALIST_LLM_*` | | 공급자를 DB에 등록하지 않았을 때의 마지막 수단 |
| `SIGNALIST_OPENAI_*` | | 레거시 폴백 키 |
| `SIGNALIST_DART_API_KEY` | | Open DART. 한국 종목의 corp_code 조회와 재무 공시에 필요 |
| `SIGNALIST_SEC_USER_AGENT` | | SEC 가 요구하는 `이름 이메일` 형식. 없으면 403 이 납니다 |
| `SIGNALIST_CACHE_URL` | | Redis 주소. 없으면 워커별 LocMemCache 를 씁니다 |

---

## 아키텍처

프로세스가 **셋**입니다. Django 웹 서버, 스케줄러, 데이터베이스. Node 는 쓰지 않습니다.

```
                        브라우저
                           │
        ┌──────────────────▼───────────────────┐
        │  Django 5.2 — 템플릿 + Admin          │
        │                                       │
        │   news/views.py       화면            │
        │   news/admin.py       운영 조회        │
        │   news/crawler/**     순수 파싱 로직   │
        │   news/services/**    DB·네트워크      │
        └──────────────────┬───────────────────┘
                           │
        ┌──────────────────▼───────────────────┐
        │  manage.py run_scheduler              │
        │                                       │
        │   crawl_due_sources()     기한 된 소스│
        │   process_pending_insights() 본문 분석│
        │   reap_stuck_runs()       멈춘 실행 정리│
        └──────────────────┬───────────────────┘
                           │ DATABASE_URL
                  ┌────────▼──────────────┐
                  │  PostgreSQL 16        │
                  │   news_sources        │
                  │   news_articles       │
                  │   news_insights       │
                  │   news_article_symbols│
                  │   news_crawl_runs     │
                  │   llm_providers       │
                  └───────────────────────┘
                           │ 외부
              ┌────────────┴──────────────┐
              │ 뉴스 사이트 · RSS          │
              │ OpenAI 호환 LLM 엔드포인트 │
              └───────────────────────────┘
```

웹 서버와 스케줄러는 **같은 코드**(`news/crawler/*`, `news/services/*`)를 공유하고 DB를 통해서만 만납니다. 스케줄러가
죽어도 웹은 살아 있고, `/news/sources`의 "지금 수집" 버튼으로 수동 실행이 가능합니다.

### 왜 이 구성인가 (히스토리)

이 저장소는 원래 **OpenAI ChatGPT 앱 템플릿**으로 생성되어 Cloudflare Workers + D1(SQLite) 위에서
돌았습니다. 최초 커밋부터 `.openai/hosting.json`, `worker/index.ts`, `vinext`, `wrangler`가 들어
있었고 D1 이름이 `site-creator-d1`이었습니다. Node·Cloudflare·vinext는 엔지니어링 판단이 아니라
**스캐폴딩 도구가 준 기본값**이었습니다.

그 플랫폼을 떠나면서 전부 평범한 것으로 바꿨습니다.

| 이전 | 이후 | 이유 |
|---|---|---|
| Cloudflare Workers | Node 프로세스 | `pg`가 Node TCP 소켓을 요구 — workerd에는 `node:net`이 없어 **선택이 아니라 강제** |
| Cloudflare D1 (SQLite) | PostgreSQL 16 | 윈도 함수·`numeric`·파티셔닝·`DISTINCT ON` 없이는 팩터 계산이 불가 |
| `vinext` → Next.js 16 → 삭제 | Django 템플릿 | Cloudflare를 떠나자 vinext는 존재 이유가 없고, Python으로 통일하면서 React도 걷어냄 |
| Worker cron 트리거 | `manage.py run_scheduler` | Worker는 상시 프로세스가 없어 플랫폼이 깨워 줬음 |
| ChatGPT 앱 헤더 인증 | `django.contrib.auth` | 플랫폼을 떠나면 `oai-authenticated-user-*` 헤더 자체가 사라짐 |
| TypeScript 전체 (~2,000줄) | Python | 언어와 프로세스를 하나로. 자세한 근거는 [이식 기록](#typescript-에서-python-으로) |

---

## 코드 구조

```
backend/
  signalist/settings/{base,dev,prod,test}.py   설정
  news/
    crawler/          순수 함수. Django 를 import 하지 않는다
      dates.py        발행시각 판독 — 가장 위험한 부분
      jsurl.py        URL 정규화 — canonical_url 계약
      html.py         JSON-LD · 앵커 오프셋 윈도 · 페이지네이션
      feed.py         RSS · Atom
      robots.py       robots.txt 판정
      fetcher.py      전체 데드라인 · SSRF · 크기 제한
      body.py         기사 본문 추출
      analysis.py     규칙 기반 감성
      keywords.py     조사 제거 키워드
      symbols.py      종목 매칭 + symbol_data.py(기계 생성 120개)
      insights.py     인사이트 조립과 검증
      llm.py          OpenAI 호환 어댑터 · 실패 분류 · 쿨다운
      window.py       수집 창
      schedule.py     다음 실행 시각
    services/         DB · 네트워크를 만지는 층
      ingest.py       수집 오케스트레이션
      insights.py     본문 분석 큐
      llm.py          공급자 페일오버
    models.py         6개 모델
    views.py forms.py 화면
    admin.py          운영 조회
    templates/news/   HTML
    management/commands/  crawl_news · analyze_news · run_scheduler
    tests/            테스트 96개 + 정답지
```

### `crawler/` 와 `services/` 를 나눈 이유

`crawler/` 는 **Django 를 import 하지 않습니다.** 순수 함수만 있고 DB·네트워크는
`services/` 가 담당합니다.

덕분에 파싱 로직 테스트가 DB 없이 돌고(96개 중 대부분), 이식 동일성을 고정 입력으로
증명할 수 있습니다. `fetcher.py` 와 `body.py` 만 `httpx` 를 쓰는데, 이들도 클라이언트를
인자로 받아 호출부가 수명을 관리합니다 — prefork 워커에서 모듈 레벨로 공유하면 소켓이
자식 간에 섞입니다.

### 화면 흐름은 Spring MVC 와 같습니다

뷰가 모델을 채워 템플릿에 넘깁니다. 이전 React 구조는 얇은 서버 껍데기가 HTML 을 내리고
브라우저가 다시 `fetch` 로 데이터를 받는 **왕복 두 번**이었고, 그래서 첫 화면에
"불러오는 중"이 보였습니다. 지금은 한 번입니다.

폼 검증은 파이프라인과 **같은 함수**를 씁니다 — `SourceForm.clean_url` 이
`validate_source_url` 을 그대로 호출합니다. 다른 규칙을 쓰면 "등록은 되는데 수집이 안 되는
소스"가 생깁니다.

---

## 데이터베이스

PostgreSQL 16. 스키마 소유자는 **Django 마이그레이션**입니다.

```bash
# news/models.py 수정 후
.venv/bin/python manage.py makemigrations news
.venv/bin/python manage.py migrate
```

**생성된 SQL을 확인하는 습관을 두세요** — `manage.py sqlmigrate news 0001`.

이식 중에는 drizzle 이 스키마를 소유하고 모델이 `managed = False` 였습니다. 소유권을
넘길 때 다음을 확인했습니다.

- 빈 DB 에 `migrate` 한 결과가 기존 DB 와 컬럼·타입·인덱스·제약까지 일치하는지
- `--fake-initial` 이 거짓이 되지 않도록 PK 를 `AutoField`(integer)로 고정 — drizzle 의
  `serial` 이 32비트이고 Django 기본값 `BigAutoField` 는 bigint 다
- 인덱스 이름을 Django 규약으로 개명(0002) — Django 는 이름을 30자로 제한하고 drizzle
  이름은 그보다 길었다
- Django 가 만드는데 drizzle 은 만들지 않던 인덱스를 채움(0003) — FK 인덱스와
  `text_pattern_ops`(LIKE 접두어 검색용)

이전 마이그레이션은 `docs/reference/` 에 보존돼 있습니다(실행 금지).

### 테이블

| 테이블 | 내용 |
|---|---|
| `news_sources` | 등록된 뉴스 사이트. 수집 시각(`crawl_hour_kst`), 목록 페이지 수(`max_pages`), 수집 창(`window_hours`), 조건부 요청 캐시(`etag`/`last_modified`), 다음 실행 시각(`next_crawl_at`) |
| `news_articles` | 수집 기사. `canonical_url` UNIQUE로 중복 제거. 경량 분석 결과와 본문 분석 큐 상태(`insight_status`) |
| `news_insights` | 본문 기반 심층 분석. 요약·키워드·업종·근거(jsonb 배열), 사용 엔진·모델, 재시도 횟수 |
| `news_article_symbols` | 기사↔종목 연결. 언급 횟수와 관련도 |
| `news_crawl_runs` | 수집 실행 이력. 성공/실패, 몇 건 가져와 몇 건 넣었는지 |
| `llm_providers` | LLM 공급자. 우선순위·일일 한도·쿨다운·성공 실패 횟수 |

### 설계상 눈여겨볼 두 가지

**`published_date_kst`는 생성 열입니다.** 앱이 쓰지 않습니다.

```sql
published_date_kst date GENERATED ALWAYS AS
  ((COALESCE(published_at, collected_at) AT TIME ZONE 'Asia/Seoul')::date) STORED
```

SQLite 시절에는 타임존을 아는 날짜 추출이 불가능해 앱이 직접 썼고, 빈 문자열로 남은 행 때문에
조회 쪽에서 `COALESCE`로 되살려야 했습니다. DB가 계산하면 그 부류의 행이 아예 생기지 않고
인덱스도 그대로 쓰입니다. `timezone(text, timestamptz)`가 IMMUTABLE이라 STORED 생성 열에 쓸 수
있습니다.

**`keywords`·`sectors`·`evidence`는 jsonb입니다.** `text`로 두면 검색이 JSON 구두점까지 훑어
배열 원소 경계를 넘어 매칭됩니다 — 실측하면 `","` 검색이 전체 행에 매칭됐습니다. jsonb는 쓰기
시점에 형식을 검증하고 GIN 인덱스로 원소 단위 질의를 받쳐 줍니다.

### D1 호환 어댑터

`db/index.ts`가 `pg` 위에 D1 문장 API를 재현합니다. Cloudflare에서 옮겨올 때 호출부 ~30곳을
그대로 두기 위해서입니다.

```ts
db.prepare(sql).bind(...params).first<T>() | .all<T>() | .run()
db.batch([stmt, ...])        // 한 트랜잭션에서 원자적 순차 실행
result.meta.changes          // 영향 행 수
```

`?` 자리표시자를 `$n`으로 변환하고(따옴표 안은 건너뜀), 드라이버 기본값이 D1과 다른 부분은 타입
파서로 맞춥니다:

```ts
types.setTypeParser(20,   (v) => Number(v));      // int8 — COUNT(*)가 문자열로 오는 것 방지
types.setTypeParser(1184, (v) => Date.parse(v));  // timestamptz → 정수 밀리초
types.setTypeParser(1082, (v) => v);              // date → 'YYYY-MM-DD' 문자열 유지
```

이걸 안 하면 조용히 형태만 바뀝니다 — `summary.total.toLocaleString()`이 천단위 구분을 잃고,
`number`로 선언된 프론트 타입에 `Date`가 들어옵니다.

`db/sql.ts`는 런타임 import가 없는 타입 전용 파일입니다. 크롤러가 드라이버에 묶이지 않게 하려는
것이고, 그래서 esbuild로 파서만 번들하는 테스트가 그대로 동작합니다.

---

## 뉴스 수집

`news/crawler/` 의 순수 함수들이 파싱을, `news/services/ingest.py` 가 DB 쓰기를 담당합니다.

`/news/sources`에 뉴스 사이트나 뉴스 목록 URL을 등록하면 그 자리에서 1회 수집하고, 이후
스케줄러가 설정한 한국시간에 하루 한 번 실행합니다.

**RSS·Atom 주소를 등록하면** 발행시각이 타임존과 함께 확정적으로 제공되므로 HTML 추론보다
정확하고 한 번에 더 많은 기사를 가져옵니다. 사이트가
`<link rel="alternate" type="application/rss+xml">`을 노출하지 않는 경우가 많으므로 피드 주소를
직접 등록하는 편이 좋습니다. HTML 목록만 있는 사이트는 `목록 페이지 수`를 올리면 최근 기사가
계속 나오는 동안 `rel=next` 또는 번호 페이저를 따라 최대 10페이지까지 이어서 수집합니다.

**안전장치**: robots.txt 확인(캐시 포함), private IP 차단, 응답 크기 2.5MB 제한, 12초 타임아웃,
ETag/Last-Modified 조건부 요청.

---

## 본문 기반 분석 파이프라인

수집기는 목록과 요약만 저장하므로, 종목·시황 분석에 쓸 근거는 별도 큐가 만듭니다. 기사마다
`insight_status`가 `대기`로 들어가고 스케줄러가 `processPendingInsights()`로 한 배치씩
소화합니다. `/news/archive`의 `본문 분석 실행` 버튼이나 `POST /api/news/insights`로 직접 돌릴
수도 있고, `GET /api/news/insights`는 큐 현황을 돌려줍니다.

1. `canonical_url`의 원문 페이지를 robots.txt를 확인한 뒤 읽어 문단 태그에서 본문만 추출합니다.
   저작권·제보 안내 같은 상투 문구는 버립니다.
2. 규칙 엔진이 조사를 떼어 키워드를 뽑고, 종목 사전으로 언급된 상장사를 찾습니다. 긴 이름을 먼저
   세기 때문에 `카카오뱅크` 기사가 `카카오`로 중복 집계되지 않고, 공유 버튼의 `카카오톡` 같은
   문구는 제외합니다. 영문 티커는 단어 경계를 지켜 오탐을 막습니다.
3. 종목이 잡혔거나 중요도가 낮지 않은 기사만 LLM으로 보내 요약·근거·시황 관점을 구조화합니다.
   무료 한도를 아끼기 위한 선별 단계이며, 호출이 실패하면 규칙 결과를 그대로 씁니다.
4. 결과는 `news_insights`에, 종목 매핑은 `news_article_symbols`에 저장합니다. **원문 본문은
   저장하지 않고** 글자 수만 남깁니다.

---

## AI 공급자 우선순위와 폴백

분석에 쓸 LLM은 `llm_providers` 표에서 관리합니다. `/news/providers` 화면에서 등록·수정하며,
우선순위가 **낮은 숫자부터** 호출합니다. 앞 공급자가 막히면 그 자리에서 다음 공급자로 넘어가고,
전부 막히면 규칙 기반 엔진으로 분석을 이어갑니다.

| 실패 종류 | 판정 기준 | 쉬는 시간 |
| --- | --- | --- |
| 한도 초과 | 429, 402, 또는 400 + quota·limit 문구 | 1시간 (한국시간 자정을 넘기지 않음) |
| 인증 오류 | 401, 403 | 6시간 |
| 요청 오류 | 그 외 4xx | 30분 |
| 일시 오류 | 5xx, 타임아웃, 네트워크 오류 | 5분 |

한도 초과가 분당 제한인지 일일 제한인지는 응답만 보고 알 수 없어 1시간을 기본으로 잡되, 자정이
더 가까우면 자정까지만 쉽니다. 무료 티어 사용량이 그때 초기화되기 때문입니다. `daily_limit`을
적어두면 호출 전에 세어 한도에 닿기 전 다음 공급자로 넘어갑니다. 사용량은 한국시간 날짜가 바뀌면
0부터 다시 셉니다.

화면에서 프리셋(Gemini, Groq, OpenRouter, Cerebras)을 고르면 base URL과 모델명이 채워집니다.
무료 한도와 모델명은 제공사가 자주 바꾸므로 `연결 확인` 버튼으로 실제 호출이 도는지 보고 모델명을
고치세요. API 키는 DB에 저장되고 화면·API 응답에는 끝 네 글자만 나갑니다.

공급자를 하나도 등록하지 않았을 때만 환경변수 설정을 마지막 수단으로 씁니다.

```bash
SIGNALIST_LLM_API_KEY=...      # 아무 공급자도 없을 때만 사용
SIGNALIST_LLM_BASE_URL=...     # 기본값 https://api.openai.com/v1
SIGNALIST_LLM_MODEL=...
SIGNALIST_LLM_TIMEOUT_MS=25000 # 선택
```

키가 하나도 없어도 규칙 기반 엔진만으로 **파이프라인 전체가 동작합니다.**

---

## TypeScript 에서 Python 으로

수집·분석 파이프라인 ~2,000줄을 이식했습니다. 이식 동일성(parity)을 먼저 증명하는 방식으로
진행했습니다.

### 정답지 방식

동결된 TypeScript 구현을 고정 입력에 돌려 출력을 JSON 으로 남기고
(`news/tests/parity/expected.json`), Python 이 같은 입력에 같은 출력을 내는지 검사합니다.

**왜 이렇게까지 하는가**: 모든 추출 경로가 날짜를 못 찾으면 기사를 조용히 버립니다. 이식판이
조금이라도 덜 관대하면 예외 없이 기사 수만 줄고 `새 기사 없음` 으로 기록됩니다. 정상처럼
보이므로 몇 주간 모릅니다.

추론 사례 143개 + 실제 언론사 피드 120건. 마지막 것은 같은 90KB 바이트를 두 구현에 돌려
**120건 × 4필드 = 480개 값 불일치 0개**를 확인한 것입니다.

### 라이브러리를 쓰지 않은 곳과 이유

| 후보 | 쓰지 않은 이유 |
|---|---|
| `dateutil` | `Date.parse` 보다 관대해서, 원본이 일부러 없앤 "기사 번호와 스코어가 그럴듯한 타임스탬프로 둔갑" 버그를 되살립니다 |
| `feedparser` | HTML 을 sanitize 해 excerpt 가 달라지고 기존 기사 전체의 `content_hash` 가 바뀝니다 |
| `beautifulsoup4` | `anchor_context` 는 원시 HTML 을 문자 오프셋(±320)으로 잘라 문맥을 만듭니다. 파싱된 트리로는 표현할 수 없고, 바꾸면 다른 기사 집합이 되며 튜닝된 상수들이 무효가 됩니다 |
| `trafilatura` | 이 크롤러는 목록 페이지만 읽습니다. 전문 추출 도구가 필요 없습니다 |
| `urllib.robotparser` | 양방향 agent prefix 매치, 최장 패턴 승리, 빈 줄 그룹 리셋 등 네 가지 동작이 재현되지 않습니다. 30줄이라 그대로 이식했습니다 |

### 이식하면서 잡은 함정

- **`Date.UTC` 오버플로** — `2026-02-30` 이 `2026-03-02` 로 정규화됩니다. Python
  `datetime` 은 예외를 던지므로 `datetime + timedelta` 누산으로 재현했습니다
- **Python `\d` 는 유니코드** — 전각 숫자가 매치됩니다. 모든 숫자 패턴에 `re.ASCII`
- **가변폭 lookbehind** — `(?<=[.!?。]|다\.)` 를 Python `re` 가 거부합니다. 고정폭 둘로
  재구성했습니다
- **`urljoin` 이 절대 URL 의 dot-segment 를 정규화하지 않습니다** — WHATWG 는 항상 합니다
- **`urljoin` 이 빈 `?` 를 버립니다** — 원문에서 판정해야 합니다
- **JS `str.replace(문자열)` 은 첫 번째만** 바꿉니다. Python 은 전부이므로 `count=1` 필수
- **JS `Math.round` 는 `.5` 를 +∞ 로** 올립니다. Python `round()` 는 짝수로 붙입니다

### 의도적으로 원본과 같게 둔 것

- **인코딩** — `TextDecoder()` 가 charset 을 무시해 EUC-KR 사이트 제목이 mojibake 인 것도
  그대로입니다. 고치면 `content_hash` 가 전부 바뀌므로 백필과 함께 별도로 해야 합니다
- **SSRF 가드** — DNS 해석 결과 검사와 IPv6 범위 검사는 원본에 없는 추가 방어입니다.
  넣으면 동일성 diff 를 해석할 수 없게 되므로 이식 후 별도 작업입니다

### `article-body` 는 크롤러와 동작이 다릅니다

같은 이름의 함수가 있지만 원본이 **의도적으로 별도 구현**을 뒀습니다. 재사용하면 조용히
틀립니다.

| | 크롤러 | 본문 추출 |
|---|---|---|
| 알 수 없는 named 엔티티 | `&entity;` 로 되돌림 | **공백**으로 바꿈 |
| 크기 초과 | 예외 | **읽은 만큼만 쓰고 중단** |
| robots 401·403·5xx | 예외 | **False 반환** |
| 상한 | 2.5MB | 1.5MB |

---

## 테스트

```bash
cd backend && .venv/bin/python -m pytest        # 96개
.venv/bin/python -m pytest -k parity            # 이식 동일성만
```

**파서 테스트**는 `tests/fixtures/`의 고정 픽스처(`news-feed.xml`, `news-list.html`)에 esbuild로
번들한 실제 소스를 돌립니다. 단정이 구체적입니다 — 스포츠 스코어(`3-2`)와 기사 번호
(`AKR20260827173200001`)를 날짜로 오인하지 않는지, `"12분 전"`·`"오늘 07:30"`을 읽는지, 12월
목록을 1월에 읽어도 연도를 되돌리는지, 수집 창 경계에서 정확히 자르는지, 긴 종목명을 먼저 세는지.

**SSR 테스트**는 `next start`를 띄우고 HTTP로 화면들을 확인합니다. 예전에는 Cloudflare Worker
export를 직접 호출했는데 그 export가 없어져 재작성했습니다.

---

## 주의할 함정

실제로 부딪혀 코드에 주석으로 남긴 것들입니다. 대부분 "동작하지만 조용히 틀린" 부류입니다.

**`us-gaap`만 파싱하면 IFRS 시기가 조용히 빕니다.** SEC `companyfacts` 는 한 회사 안에
`us-gaap` 과 `ifrs-full` 이 섞여 있을 수 있습니다(IREN 은 340개 + 202개). us-gaap 만 읽으면
IFRS 로 보고하던 기간이 0 이 아니라 **없음**으로 나와 리포트가 무이익으로 오독합니다. 그래서
공시 근거는 XBRL 이 아니라 `submissions` 메타데이터로 만듭니다(`research/sec_profile.py`).

**외국 발행사(FPI)에는 10-Q 가 없습니다.** 20-F 로 연차를, 6-K 로 수시 보고합니다. 분기
데이터가 없는 것을 "공시 지연"으로 해석하면 안 됩니다.

**설립지와 보고 양식은 별개입니다.** 미국 밖 법인이 FPI 지위를 벗고 10-K/10-Q 로 보고할 수
있습니다. IREN(호주 법인)이 2024년까지 20-F, 2025년부터 10-K 입니다. 그래서 프로필은
`reporting_regime`(양식)과 `is_non_us_incorporated`(설립지)를 따로 둡니다. 양식 전환은
`changed_regime` 으로 잡는데, 이것이 `companyfacts` 의 taxonomy 혼재를 그대로 설명합니다 —
20-F 시절 `ifrs-full`, 10-K 전환 후 `us-gaap` 입니다.

**'국내/외국' 라벨에는 기준 국가를 못 박습니다.** 이 프로젝트는 한국 사용자를 향하는데
SEC 용어의 domestic 은 미국 기준입니다. 기준점 없이 "국내"라고 쓰면 코스피로 읽힙니다.
그래서 라벨을 `미국 내국법인 양식(10-K·10-Q)` / `미국 기준 외국법인 양식(20-F)` 처럼
어느 나라 기준인지 문구에 담았습니다.

**`Host` 헤더를 직접 넣지 않습니다.** httpx 가 URL 에서 설정합니다. 하드코딩하면 같은
클라이언트를 다른 서브도메인에 쓸 수 없습니다 — SEC 티커 목록은 `www.sec.gov` 에, 나머지
API 는 `data.sec.gov` 에 있습니다.

**DART `corpCode.xml` 은 Content-Type 이 거짓말입니다.** `application/x-msdownload` 로 오지만
실체는 ZIP 입니다. 게다가 키가 틀리면 ZIP 도 아닌 평문 XML(`<status>013</status>`)이 옵니다.

**공시기관 목록에는 정식 사명만 있습니다.** `corpCode.xml` 과 `company_tickers.json` 은
'삼바'·'한전'·'엔비디아' 같은 통칭이나 옛 사명(대우조선해양 → 한화오션)을 모릅니다. 뉴스
매칭용으로 이미 관리하는 `news/crawler/symbol_data.py` 의 별칭 사전을 마지막 폴백으로
빌려 씁니다 — 같은 사전을 두 벌 관리하지 않으려는 것입니다.

**SEC 티커 매핑에 모든 종목이 있는 것은 아닙니다.** EDGAR 에 직접 보고하는 발행사만 들어갑니다.
SPY·TSM 처럼 스스로 보고하는 ETF·ADR 은 있지만, 펀드의 개별 시리즈(VOO)나 비후원 ADR(NSRGY)은
없습니다. 미등재는 오류가 아니라 정상적인 "없음"이라 공시 근거 없이 진행합니다.

**`sync_to_async` 는 `thread_sensitive=False` 여야 합니다.** 기본값이면 메인 스레드 실행기에
직렬화돼 비동기로 뺀 이득이 사라집니다.

**jsonb `?` 연산자와 자리표시자 `?`가 충돌합니다.** 어댑터가 `?`를 `$n`으로 바꾸므로
`keywords ? 'x'`를 쓸 수 없습니다. `jsonb_exists()`는 `?`를 피하지만 **GIN 인덱스를 잃습니다**
(실측: `@>`와 `?`는 Bitmap Heap Scan, `jsonb_exists`는 Seq Scan). **`@>`가 유일하게 양쪽을
만족**합니다 — `keywords @> '["x"]'::jsonb`.

**jsonb는 읽기와 쓰기가 비대칭입니다.** 드라이버는 조회 결과를 파싱된 배열로 주지만, 파라미터로
받은 JS 배열은 Postgres 배열 리터럴 `{a,b}`로 직렬화해 jsonb 파싱이 실패합니다. 쓰기에는
`JSON.stringify`가 필요합니다. (객체는 JSON으로 직렬화되지만 배열은 그렇지 않습니다.)

**`to_timestamp(ms/1000)`은 초 미만을 절삭합니다.** 정수 나눗셈입니다.
`ms::double precision / 1000`이어야 합니다. 특히 `next_crawl_at`(미래 시각)이 틀리면 모든 소스
스케줄이 밀립니다.

**Postgres `GROUP BY`는 SQLite보다 엄격합니다.** `GROUP BY symbol`에서 `company`를 선택할 수
없습니다(PK가 아니라 함수종속 불성립). `GROUP BY s.id`는 PK라 유효합니다.

**수집 실행 행은 네트워크 I/O 전에 커밋합니다.** 전체를 한 트랜잭션으로 감싸면 진행 중인 실행이
보이지 않고, 최대 10페이지 × 12초 동안 트랜잭션이 열려 vacuum을 방해합니다.

**시각 바인딩에 추측을 넣지 않았습니다.** 파서는 정수 밀리초로 동작하고 컬럼은 `timestamptz`라,
SQL 경계에서 명시적 `at(ms)`로 변환합니다. 새 바인딩에서 빠뜨리면 Postgres가 곧바로 타입 오류를
내므로 조용히 틀리지 않습니다.

---

## 추천 모델 교정 내용

정량 랭커와 AI 해석 계층의 첫 실행 경로가 구현되어 있습니다. 가격·재무 데이터 공급자와
일일 추천 저장 배치는 아직 연결 전이며, 아래는 그 확장 설계입니다.

- PER·PBR은 반드시 봅니다. 다만 낮다는 이유만으로 추천하지 않고 업종 내 백분위, Forward PER, PBR/ROE, EV/EBITDA, 이익 성장과 같이 봅니다.
- Quality에는 매출총이익/자산, ROE, 현금전환, 레버리지, 이익 안정성을 포함합니다. 수익성은 가치와 독립적인 설명력을 가진다는 연구를 반영했습니다.
- Momentum은 12-1개월, 6-1개월, 1개월 추세와 52주 고점 거리로 구성하되 고변동성 반등장에서 급락할 수 있으므로 VIX 기반 국면 조절을 적용합니다.
- Earnings revisions는 최근 실적 서프라이즈, EPS 컨센서스 변화, 추정치 확산도를 사용합니다. 무료 데이터만으로 컨센서스를 구할 수 없으면 해당 팩터 신뢰도를 낮춥니다.
- 뉴스는 단순 긍·부정이 아니라 종목 관련성, 중요도, 새로움, 출처 신뢰도, 사건 중복을 평가합니다. 동일 사건 기사를 클러스터링해 여론 복제를 점수로 오인하지 않습니다.
- VIX/V-KOSPI, USD/KRW, 미 국채 10년·한국 3년, 장단기 금리차, 신용스프레드를 시장 전체 위험예산과 업종 민감도에 반영합니다.
- 거래대금, 스프레드, 거래정지, 관리종목, 데이터 결측/지연을 하드 필터로 두고 백테스트에는 수수료·슬리피지·상장폐지 종목을 포함합니다.

연구 근거: [Fama/French Research Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library.html), [Novy-Marx의 수익성 프리미엄](https://www.nber.org/papers/w15940), [AQR Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk), [Daniel·Moskowitz Momentum Crashes](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2490306), [Cboe VIX](https://www.cboe.com/tradable-products/vix).

### 제품 흐름 (목표)

1. 장 마감 후 가격·재무·거시·뉴스 데이터를 수집하고 `available_at` 기준으로 시점을 고정합니다.
2. 유동성·데이터 신선도 필터 후 Quality, Value, Momentum, Revisions, News, Risk 팩터를 횡단면 정규화합니다.
3. VIX, 원/달러, 미 국채 10년물, 신용스프레드가 위험회피 국면을 만들면 Momentum 비중을 낮추고 Quality·Value 비중을 높입니다.
4. 매일 시장별 상위 5개를 저장합니다. 절대 기준 미달 종목은 목록에서 숨기지 않고 `관찰`로 표시합니다.
5. 목표가·매수구간·손절가는 ATR과 위험예산으로 정량 엔진이 계산합니다. LLM은 숫자를 바꾸지 않고 재무·뉴스 근거, 반대 논리, 무효화 조건을 구조화합니다.
6. 사용자가 재분석하면 최신 데이터 컷오프로 새 버전을 저장하고 과거 보고서는 보존합니다.

`POST /api/research/stocks/{symbol}/analyze`는 두 가지 방식으로 부를 수 있습니다.

```jsonc
{"symbols": ["005930.KS", "000660.KS", "NVDA"]}   // 서버가 시세를 받아 팩터 점수를 계산
{"candidates": [...], "regime": {...}}            // 팩터 점수를 직접 넘김(기존 계약)
```

`symbols` 를 주면 `research/scoring.py` 가 시세·재무·뉴스 감성에서 팩터 점수를 만들고
`research/macro.py` 가 VIX·원달러·미10년물로 국면을 잡습니다. `candidates` 를 주면 그 값을
그대로 씁니다 — 예제 입력은 `docs/examples/stock-analysis-request.json` 에 있습니다.

AI는 투자 논리·반대 논리·촉매·무효화 조건만 작성하며 점수·판단·신뢰도·매수구간·목표가·손절가는
응답에 어떤 값을 넣더라도 정량 엔진 값으로 고정됩니다. AI 공급자가 모두 실패하면 정량 보고서를
반환합니다.

이 엔드포인트는 브라우저 폼이 아니라 프로그램이 호출하는 JSON API 라 **CSRF 를 면제**했습니다.
조회·계산만 하고 DB 를 바꾸지 않아 위조 요청으로 상태가 변할 여지가 없습니다. 다만 호출마다
시세 조회와 LLM 비용이 들므로, 공개 배포한다면 인증이나 호출 한도를 앞에 두어야 합니다.
화면용 폼 뷰(`/research/rank`, `/research/lab`)는 CSRF 보호를 그대로 유지합니다.

브라우저에서는 `/research/rank` 가 같은 일을 합니다. 종목명을 입력하면 자동완성이 뜨고,
고른 종목들을 점수로 줄 세운 뒤 각 행에서 AI 분석으로 넘어갑니다.

브라우저의 `/research/lab`에는 `IREN`, `NVDA`, `005930.KS` 같은 티커를 직접 입력하거나
검색 자동완성으로 고를 수 있습니다(국내는 KIS 종목마스터, 미국은 SEC 등록 티커).
프로젝트가 Yahoo Finance에서 최근 1년 가격, 주요 재무 항목과 관련 뉴스 제목·요약을 수집한 뒤
등록된 AI 공급자에 근거로 전달합니다. AI 응답에는 목표가를 요구하지 않으며 상승 논리, 반대 논리,
촉매, 무효화 조건과 데이터 한계를 표시합니다. Yahoo Finance 데이터는 개인 연구·교육 목적의
테스트용이며 지연·누락될 수 있습니다.

### 배치 권장 주기

| 작업 | 권장 주기 | 비고 |
|---|---:|---|
| 가격/거시 스냅샷 | 장중 1~5분, 장 마감 확정 | 공급자 제한 준수 |
| 공시·재무 | 5~15분 | 공시시각 그대로 보존 |
| 뉴스 피드 | 2~10분 | 소스별 rate limit |
| 뉴스 분류/클러스터 | 수집 직후 | 경량 모델 + 캐시 |
| 일일 추천 | 시장별 장 마감 후 1회 | 데이터 품질 검사 후 publish |
| 사용자 AI 재분석 | 요청 시 | 동일 cutoff는 idempotency 처리 |

`price_bars`는 **첫날부터 월별 파티셔닝**으로 만드세요. 1분봉 × ~2800 KRX 종목 × 390봉/일 ≈
110만 행/일, 4억 행/년입니다. 4억 행에서 소급 파티셔닝은 주말 다운타임입니다.

---

## 데이터 수집 원칙

- 저작권 위험을 낮추기 위해 공개 목록이 제공한 제목·요약과 원문 링크만 보관하며, 전문 재게시를 하지 않습니다. 저작권·삭제 요청 대응을 위해 원문과 파생 요약을 분리합니다.
- RSS·Atom·JSON-LD·HTML 시간 태그 순으로 발행일을 식별합니다. HTML에서는 `<time datetime>`과 `class`·`id`에 시각을 표기한 전용 요소를 먼저 읽습니다. 목록 항목이 기사 본문 전체를 리드로 싣고 그 뒤에 발행시각을 두는 구조가 흔하기 때문입니다. **날짜 토큰이 확인되지 않으면 기사를 버리며**, 주변 텍스트를 통째로 `Date.parse`에 넣지 않습니다. 기사 번호나 이미지 경로의 숫자가 발행일로 둔갑하기 때문입니다.
- 로그인이 필요한 페이지, 유료 기사, 내부망 주소는 제외하고 범용 판독이 어려운 사이트는 허용 정책을 확인한 전용 어댑터를 추가합니다.
- 수집 대상은 한국시간 날짜가 아니라 **발행 후 경과 시간**으로 고릅니다. 미국 매체가 현지 오후에 낸 기사는 한국시간으로 어제와 오늘에 걸쳐 흩어지므로 같은 날짜 비교로는 대부분 누락됩니다. 하루 한 번 실행에 36시간 창을 쓰면 12시간이 겹쳐 빈 구간이 생기지 않고, 겹치는 부분은 `canonical_url` 유니크 인덱스가 흡수합니다. 해외 매체는 48시간 이상을 권장합니다. 발행시각이 미래로 찍힌 경우는 2시간까지 허용합니다.
- 피드 시각에 타임존이 없으면 한국시간으로 해석합니다. `Date.parse`는 이런 문자열을 실행 환경의 로컬 시간대로 읽는데, 개발 환경은 KST이고 서버는 보통 UTC라 그대로 두면 국내 피드 기사가 9시간 미래로 기록되어 전부 탈락합니다. 같은 이유로 컨테이너는 `TZ=UTC`로 고정하고, 한국시간 날짜는 `published_date_kst` 생성 열이 `Asia/Seoul`로 계산합니다.
- 기사 URL 정규화와 본문 해시로 중복을 제거합니다. `utm_*`과 `section`, `cp`, `ref` 같은 목록·캠페인 쿼리는 정규화 단계에서 제거해 같은 기사가 경로만 달리해 두 번 저장되지 않게 합니다. **이 정규화는 이제 영구 계약입니다** — strip 목록을 바꾸면 이미 저장된 기사의 중복 행이 생기므로 정규화기를 버전화하고 변경 시 전체 재정규화가 필요합니다.
- 한국 재무는 Open DART, 미국 재무는 SEC `data.sec.gov`, 시장 통계는 계약 범위 내 KRX/KIS 등 증권 API, 거시는 한국은행 ECOS·FRED·Cboe를 우선 검토합니다. SEC의 공개 XBRL/제출 API는 키 없이 제공되며 실시간으로 갱신됩니다.

---

## Point-in-time 저장 설계

`api/migrations/001_initial.sql`에 17개 테이블 설계가 있습니다 — 종목·OHLCV·재무·밸류에이션·거시
관측치, 뉴스 원문·버전·사건 클러스터·종목 연결, 관심종목과 포지션, 추천 실행·결과·분석 근거.

**한 번도 실행된 적 없는 설계 문서입니다.** 참조용으로만 보고 그대로 `psql -f` 하지 마세요 —
4개 테이블에 RLS를 켜고 정책을 0개 정의해 일반 롤에 deny-all이 됩니다.

핵심은 모든 관측 데이터가 `observed_at`(사실이 기술하는 시점)과 `available_at`(우리가 알 수
있었던 시점)을 **분리**한다는 점입니다. 이 분리가 없으면 공시 수정값이나 늦게 들어온 데이터를
과거 백테스트에 사용하는 look-ahead bias가 생깁니다.

강제 지점은 애플리케이션이 아니라 **DB**여야 합니다. 팩터 계산은 성능상 ORM을 우회해 raw
SQL/pandas로 가게 되므로, ORM 레이어의 필터는 정작 bias가 발생하는 경로를 보지 못합니다.
`pit` 스키마에 `current_setting('app.as_of')`로 필터하는 뷰를 두고 분석용 DB 롤에게 base 테이블
권한을 주지 않으면, look-ahead가 raw SQL과 pandas에도 동일하게 적용되는 **권한 오류**가 됩니다.
여기에 `CHECK (available_at >= observed_at)`과 공급자별 지연 적용 테스트를 더합니다.

---

## 앞으로

### 정리 대상

- **`api/`** — FastAPI 프로토타입 16개 파일. DB 코드가 0줄이고(SQLAlchemy·asyncpg는 선언만),
  Redis/Celery도 0줄, 프론트가 한 번도 호출하지 않으며 2주 넘게 정체했습니다. 보존 가치는
  `api/app/domain/recommendation.py`의 `rank_candidates` **67줄**뿐입니다 — 순수 stdlib으로
  eligibility 필터, winsorized z-score 횡단면 정규화, VIX/환율/신용스프레드 기반 국면 가중치
  조절, ATR 위험예산 목표가까지 완성돼 있고 테스트 2개가 붙어 있습니다.
- **`app/data.ts`** — 리서치 엔진이 실제 데이터를 내기 시작하면 삭제합니다.

### 리서치 엔진

별도 서비스로 두고, TypeScript가 소유한 뉴스 테이블은 그대로 둡니다. **한 테이블에 두 소유자를
두지 않는다**는 규칙만 지키면 두 언어가 한 DB를 공유하는 것은 정상 아키텍처입니다.

첫 슬라이스로 권하는 것은 **읽기 전용 관리 화면**입니다. 예를 들어 Django라면
`managed = False` 모델로 뉴스 테이블을 Admin에 얹으면 스키마 소유권 충돌 없이 하루 만에 크롤
실패 추적·큐 적체 확인·공급자 사용량을 화면으로 얻습니다. 그다음이 `rank_candidates`를 실제
데이터에 연결해 대시보드의 mock을 대체하는 작업이고, 여기서야 `instruments`·`valuation_snapshots`
같은 PIT 테이블이 필요해집니다.

이 순서가 중요한 이유는 `api/`가 죽은 이유가 그것이기 때문입니다 — 아무것도 실제로 소유하지 않는
패러렐 프로토타입이었고, 프론트가 한 번도 호출하지 않았습니다. 첫 주에 눈에 보이는 것을 만들지
않으면 같은 일이 반복됩니다.

### 운영 전 체크

- 데모 시세를 실제 증권 API 어댑터로 교체
- 사용자 인증과 사용자별 데이터 격리 (현재 인증 없음)
- LLM 키, DB URL, 공급자 키를 secret manager에 등록
- 워크포워드 검증, 퍼지 기간, 거래비용을 포함한 Champion/Challenger 백테스트
- 추천 결과에 데이터 기준시각, 모델 버전, 근거 링크, 투자 위험 고지 노출

---

이 서비스는 투자 참고용 리서치 도구이며 투자자문이나 수익 보장을 제공하지 않습니다.

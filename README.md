# Signalist

Signalist는 공개 뉴스 목록을 수집하고, 기사 요약·감성·키워드·영향 업종·종목 언급을 구조화해 보여 주는 Django 기반 뉴스 리서치 워크스페이스입니다.

현재 제공 범위는 뉴스 수집·분석, 단일 종목 AI 분석, 종목 비교 랭킹입니다. 백테스트와 사용자별 포트폴리오 기능은 제공하지 않습니다.

## 기능

- RSS·Atom·HTML 뉴스 목록 수집
- robots.txt, URL 검증, 응답 크기·시간 제한을 적용한 안전한 외부 요청
- 발행 시각과 URL 정규화에 기반한 최근 기사 선별·중복 제거
- 규칙 기반 감성·중요도·키워드·종목 언급 분석
- 선택적인 OpenAI 호환 LLM 보강 분석과 공급자별 한도·쿨다운·폴백
- 기사 아카이브 검색, 즉석 분석, Django Admin 기반 운영 조회
- 공개 시장·공시·뉴스 근거를 이용한 단일 한국/미국 종목 AI 분석
- 팩터·거시 환경 기반의 종목 비교 랭킹

## 시작하기

```bash
docker compose up -d
cd backend
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp ../.env.example ../.env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

별도 터미널에서 스케줄러를 실행합니다.

```bash
cd backend
.venv/bin/python manage.py run_scheduler
```

개발 서버는 `http://localhost:8000`에서 열립니다.

## 주요 화면과 명령

| 경로 또는 명령 | 목적 |
| --- | --- |
| `/` | 소스, 최근 기사, 분석 큐, 공급자, 수집 실행 상태 |
| `/news/sources` | 뉴스 소스 등록, 수동 수집, 중지, 삭제 |
| `/news/archive` | 기사 검색·필터와 본문 분석 실행 |
| `/news/providers` | LLM 공급자 등록·연결 확인·운영 |
| `/news/lab` | 저장하지 않는 즉석 분석 |
| `/research/lab` | 한국·미국 종목의 시장·공시·뉴스 근거 기반 AI 분석 |
| `/research/rank` | 여러 종목의 팩터 점수와 거시 환경을 반영한 비교 랭킹 |
| `/research/api-test` | DART·SEC 연동 확인 |
| `/admin/` | 수집 실행, 기사, 인사이트, 공급자 운영 조회 |
| `crawl_news` | 기한이 된 소스 또는 지정 소스 수집 |
| `analyze_news` | 대기 중 기사 본문 분석 |
| `run_scheduler` | 수집·분석을 주기적으로 실행 |

## 아키텍처

```text
브라우저 ──→ Django views/templates ──→ news/services ──→ PostgreSQL
                                          │
                                          ├─→ 뉴스 사이트·RSS/Atom
                                          └─→ OpenAI 호환 LLM(선택)

브라우저 ──→ research views ──→ 시장 데이터·DART·SEC·뉴스 근거 ──→ LLM(선택)

news/crawler: URL·날짜·피드·HTML·본문·규칙 분석·LLM 응답 검증
```

`backend/news/crawler/`는 파싱과 분석 규칙을, `backend/news/services/`는 DB 기록·네트워크 호출·큐 처리를 담당합니다. 화면, 폼, Admin, 관리 명령은 입출력 변환과 유스케이스 호출에 집중합니다.

`backend/research/`는 종목 검색, 시장·공시 데이터 조회, 팩터 점수화, 거시 환경 판정, AI 보고서 생성을 담당합니다. 리서치 분석은 요청 시 생성하며 결과를 DB에 저장하지 않습니다.

## 데이터 모델

| 테이블 | 내용 |
| --- | --- |
| `news_sources` | 뉴스 소스 설정, 수집 시각, 수집 창, 조건부 요청 캐시 |
| `news_crawl_runs` | 소스별 수집 시도와 결과 |
| `news_articles` | 제목, 목록 요약, 표준 URL, 발행·수집 시각, 경량 분석 |
| `news_insights` | 본문 기반 요약·키워드·업종·근거·분석 엔진 정보 |
| `news_article_symbols` | 기사와 종목 사전 항목의 연결 |
| `llm_providers` | 공급자 설정, 우선순위, 사용량, 쿨다운 |

기사의 `canonical_url`은 유일하며 중복 저장을 막습니다. 한국시간 게시일은 PostgreSQL 생성 열이 계산합니다. 기사 본문은 분석 입력으로만 쓰고 저장하지 않습니다.

## 환경 변수

| 변수 | 용도 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 연결 문자열 |
| `DJANGO_SECRET_KEY` | 운영 환경 Django 비밀 키 |
| `DJANGO_ALLOWED_HOSTS` | 운영 허용 호스트 목록 |
| `SIGNALIST_LLM_API_KEY` | DB 공급자가 없을 때만 사용하는 LLM 키 |
| `SIGNALIST_LLM_BASE_URL` | OpenAI 호환 API 기본 URL |
| `SIGNALIST_LLM_MODEL` | 사용할 모델명 |
| `SIGNALIST_LLM_TIMEOUT_MS` | LLM 요청 제한 시간(5~60초) |
| `SIGNALIST_DART_API_KEY` | Open DART 공시 조회 키 |
| `SIGNALIST_SEC_USER_AGENT` | SEC EDGAR 요청용 `이름 이메일` 식별자 |
| `SIGNALIST_NAVER_CLIENT_ID` / `SIGNALIST_NAVER_CLIENT_SECRET` | 국내 종목 뉴스 검색용 네이버 애플리케이션 키 |
| `SIGNALIST_KIS_APP_KEY` / `SIGNALIST_KIS_APP_SECRET` | 한국투자증권 시세·수급 조회 키 |
| `SIGNALIST_CACHE_URL` | 리서치 인덱스 공유 캐시 URL(선택) |

기본 개발용 DB 연결 값은 [`.env.example`](.env.example)에 있습니다.

## 검증

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

뉴스 파서의 날짜·URL·HTML·피드·본문·분석·수집 창 동작은 고정 회귀 입력으로 검증합니다. 실제 외부 뉴스 사이트나 실제 API 키에 의존하지 않는 테스트를 유지합니다.

## 문서

도메인 계약과 운영 기준은 [문서 색인](docs/README.md)에서 확인하세요.

## 운영 주의사항

- 소스와 공급자 관리 화면에는 현재 별도 인증·인가가 없습니다. 인터넷 공개 배포 전 접근 제어를 추가해야 합니다.
- LLM API 키는 DB에 저장될 수 있으므로 운영 환경에서는 시크릿 관리와 최소 권한 DB 계정을 적용해야 합니다.
- 원문 삭제 요청·보존 기간·백업 및 복구 절차는 배포 환경에 맞게 별도로 정해야 합니다.

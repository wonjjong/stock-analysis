# Signalist

재무제표, 가격·수급, 뉴스와 거시경제를 함께 해석하는 AI 주식 리서치 워크스페이스입니다. 현재 저장소에는 완성형 프론트 데모, 결정론적 추천 엔진, OpenAI 기반 분석 서비스, 뉴스 수집기, PostgreSQL 스키마가 포함됩니다.

`/news`의 뉴스 분석실에서는 종목과 기사 본문을 입력해 관련성, 감성, 중요도, 영향 기간, 핵심 근거와 추천점수 조정치를 확인할 수 있습니다. OpenAI 키가 없으면 규칙 기반 데모 엔진, 키가 있으면 GPT-5.6 Terra의 구조화 출력이 사용됩니다.

`/news/sources`에서는 RSS·Atom 또는 피드 링크가 선언된 뉴스 목록 URL을 등록할 수 있습니다. 등록 시 즉시 첫 수집을 실행하고, 이후 Cloudflare Worker Cron이 매시간 기한이 된 소스를 찾아 각 소스의 설정된 한국시간에 하루 한 번 수집합니다. 제목·요약·발행시각·출처 URL과 경량 영향 분석은 D1에 저장되며 기사 URL 기준으로 중복을 제거합니다.

## 실행

```bash
npm install
npm run dev
```

웹은 `http://localhost:3000`에서 확인합니다. API는 Python 3.11 이상 환경에서 다음과 같이 실행합니다.

```bash
cd api
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

## 제품 흐름

1. 장 마감 후 가격·재무·거시·뉴스 데이터를 수집하고 `available_at` 기준으로 시점을 고정합니다.
2. 유동성·데이터 신선도 필터 후 Quality, Value, Momentum, Revisions, News, Risk 팩터를 횡단면 정규화합니다.
3. VIX, 원/달러, 미 국채 10년물, 신용스프레드가 위험회피 국면을 만들면 Momentum 비중을 낮추고 Quality·Value 비중을 높입니다.
4. 매일 시장별 상위 5개를 저장합니다. 절대 기준 미달 종목은 목록에서 숨기지 않고 `관찰`로 표시합니다.
5. 목표가·매수구간·손절가는 ATR과 위험예산으로 정량 엔진이 계산합니다. GPT는 숫자를 바꾸지 않고 재무·뉴스 근거, 반대 논리, 무효화 조건을 구조화합니다.
6. 사용자가 재분석하면 최신 데이터 컷오프로 새 버전을 저장하고 과거 보고서는 보존합니다.

```text
Market / Filing / Macro / News providers
                  │
          ingestion + validation
                  │
      PostgreSQL point-in-time store
          │                    │
 daily factor ranker       evidence builder
          │                    │
 recommendations ─────── AI analyst report
          │                    │
          └──── FastAPI ───────┘
                     │
             Signalist dashboard
```

## 추천 모델 교정 내용

- PER·PBR은 반드시 봅니다. 다만 낮다는 이유만으로 추천하지 않고 업종 내 백분위, Forward PER, PBR/ROE, EV/EBITDA, 이익 성장과 같이 봅니다.
- Quality에는 매출총이익/자산, ROE, 현금전환, 레버리지, 이익 안정성을 포함합니다. 수익성은 가치와 독립적인 설명력을 가진다는 연구를 반영했습니다.
- Momentum은 12-1개월, 6-1개월, 1개월 추세와 52주 고점 거리로 구성하되 고변동성 반등장에서 급락할 수 있으므로 VIX 기반 국면 조절을 적용합니다.
- Earnings revisions는 최근 실적 서프라이즈, EPS 컨센서스 변화, 추정치 확산도를 사용합니다. 무료 데이터만으로 컨센서스를 구할 수 없으면 해당 팩터 신뢰도를 낮춥니다.
- 뉴스는 단순 긍·부정이 아니라 종목 관련성, 중요도, 새로움, 출처 신뢰도, 사건 중복을 평가합니다. 동일 사건 기사를 클러스터링해 여론 복제를 점수로 오인하지 않습니다.
- VIX/V-KOSPI, USD/KRW, 미 국채 10년·한국 3년, 장단기 금리차, 신용스프레드를 시장 전체 위험예산과 업종 민감도에 반영합니다.
- 거래대금, 스프레드, 거래정지, 관리종목, 데이터 결측/지연을 하드 필터로 두고 백테스트에는 수수료·슬리피지·상장폐지 종목을 포함합니다.

연구 근거: [Fama/French Research Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library.html), [Novy-Marx의 수익성 프리미엄](https://www.nber.org/papers/w15940), [AQR Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk), [Daniel·Moskowitz Momentum Crashes](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2490306), [Cboe VIX](https://www.cboe.com/tradable-products/vix).

## 데이터 수집 원칙

- 현재 자동 수집기는 D1의 `news_sources`, `news_articles`, `news_crawl_runs`에 소스·기사·실행 이력을 저장합니다. 저작권 위험을 낮추기 위해 피드가 공개한 제목·요약과 원문 링크만 보관하며, 전문 재게시를 하지 않습니다.
- RSS·Atom·공식 API·라이선스 피드를 우선합니다. 로그인이 필요한 페이지, 유료 기사, 내부망 주소, RSS를 제공하지 않는 일반 페이지는 범용 수집 대상에서 제외하고 필요할 때 사이트별 허용 정책을 확인한 어댑터를 추가합니다.
- 기사 URL 정규화와 본문 해시로 중복을 제거하고, 동일 사건은 `news_clusters`로 묶습니다. 저작권·삭제 요청 대응을 위해 원문과 파생 요약을 분리합니다.
- 한국 재무는 Open DART, 미국 재무는 SEC `data.sec.gov`, 시장 통계는 계약 범위 내 KRX/KIS 등 증권 API, 거시는 한국은행 ECOS·FRED·Cboe를 우선 검토합니다. SEC의 공개 XBRL/제출 API는 키 없이 제공되며 실시간으로 갱신됩니다.

## 저장 구조

`api/migrations/001_initial.sql`은 다음을 포함합니다.

- 종목, OHLCV, 재무, 밸류에이션, 거시 관측치
- 뉴스 원문·버전·사건 클러스터·종목 연결
- 관심종목과 포지션
- 추천 실행과 결과, 분석 작업·버전·근거
- 모든 핵심 데이터의 `observed_at`과 `available_at` 분리

이 분리가 없으면 공시 수정값이나 늦게 들어온 데이터를 과거 백테스트에 사용하게 되는 look-ahead bias가 발생합니다.

## 배치 권장 주기

| 작업 | 권장 주기 | 비고 |
|---|---:|---|
| 가격/거시 스냅샷 | 장중 1~5분, 장 마감 확정 | 공급자 제한 준수 |
| 공시·재무 | 5~15분 | 공시시각 그대로 보존 |
| 뉴스 피드 | 2~10분 | 소스별 rate limit |
| 뉴스 분류/클러스터 | 수집 직후 | 경량 모델 + 캐시 |
| 일일 추천 | 시장별 장 마감 후 1회 | 데이터 품질 검사 후 publish |
| 사용자 AI 재분석 | 요청 시 | 동일 cutoff는 idempotency 처리 |

## 운영 전 체크

- 데모 시세를 실제 증권 API 어댑터로 교체
- Supabase/Postgres migration과 사용자별 RLS 정책 적용
- OpenAI 키, DB URL, 공급자 키를 secret manager에 등록
- 워크포워드 검증, 퍼지 기간, 거래비용을 포함한 Champion/Challenger 백테스트
- 추천 결과에 데이터 기준시각, 모델 버전, 근거 링크, 투자 위험 고지 노출

이 서비스는 투자 참고용 리서치 도구이며 투자자문이나 수익 보장을 제공하지 않습니다.

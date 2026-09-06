# 운영 정책

## 프로세스

운영에는 PostgreSQL, Django 웹 서버, 스케줄러가 필요하다. 웹과 스케줄러는 같은 코드와 DB를 공유하며 서로 직접 통신하지 않는다.

```bash
docker compose up -d
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
.venv/bin/python manage.py run_scheduler
```

개발에서 스케줄러는 기본 60초마다 기한이 된 소스와 분석 큐를 확인한다. 운영에서는 상시 `run_scheduler` 또는 외부 cron/systemd timer로 `crawl_news`, `analyze_news`를 실행할 수 있다. 동일 소스를 여러 워커가 동시에 수집하도록 설계되어 있지 않으므로, 현재는 수집 스케줄러를 한 인스턴스만 운용한다.

## 명령과 관측

| 명령 | 용도 |
| --- | --- |
| `crawl_news --source ID` | 특정 활성 소스 즉시 수집 |
| `crawl_news --limit N` | 기한이 된 소스를 최대 N개 수집(기본 20) |
| `analyze_news --limit N` | 대기 기사 본문 분석 |
| `analyze_news --stats` | 큐·엔진·LLM 설정 현황만 조회 |
| `run_scheduler --once` | 수집·분석 tick을 한 번만 실행 |
| `run_scheduler --interval N --batch N` | 주기와 tick당 분석량 조정 |

`/healthz`는 DB 연결과 핵심 뉴스 테이블의 행 수를 JSON으로 반환한다. `/admin/`은 수집 실행, 기사, 인사이트를 읽기 전용 관측 테이블로 보여 주며, 소스와 공급자는 제한적으로 조정할 수 있다.

## 장애 대응

| 증상 | 확인 | 대응 |
| --- | --- | --- |
| 소스가 `오류` | `last_error`, `NewsCrawlRun` | URL·robots·네트워크·응답 크기를 확인하고 소스를 수정/중지 |
| `실행 중`이 오래 지속 | 수집 실행 시작 시각 | 다음 scheduler tick이 30분 지난 실행을 자동 오류 처리. 프로세스 상태 확인 |
| 대기 큐 적체 | `analyze_news --stats` | 배치를 최대 50 안에서 조정하고 본문 접근·LLM 상태 확인 |
| LLM 미사용/실패 | 공급자 화면의 상태·쿨다운·한도 | 키·모델·Base URL을 연결 확인, 필요 시 쿨다운 해제. 규칙 분석은 계속됨 |
| 신규 기사가 0 | 실행의 fetched/inserted 수 | 304, 수집 창, 중복 URL, 발행일 판독을 구분해 확인 |

소스 삭제는 연결된 기사·인사이트·수집 실행을 CASCADE로 삭제한다. 운영자는 삭제 전 아카이브 보존 필요성을 판단해야 한다. 현재 복구용 백업·보존 정책은 저장소에 자동화되어 있지 않다.

## 배포 전 최소 점검

- `DJANGO_SECRET_KEY`와 `DJANGO_ALLOWED_HOSTS`를 설정하고 production settings를 사용한다.
- TLS 종료 지점과 `SECURE_SSL_REDIRECT`가 일관되는지 확인한다.
- DB 백업·복구 절차와 API 키 저장 방식을 운영 환경에 맞춰 확정한다.
- 공개 노출 전 접근 제어 공백을 해소한다.
- `pytest`와 `ruff check .`를 통과시킨 배포본만 사용한다.

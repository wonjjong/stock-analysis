# 아키텍처 정책

## 목적

비즈니스 규칙을 프레임워크·외부 서비스·DB 세부사항에서 분리하여, 파싱 규칙과 투자 계산을 독립적으로 검증하고 외부 연동의 변경 범위를 좁힌다.

## 계층과 허용 의존성

```text
입출력: views / forms / templates / admin / management commands
                         ↓
애플리케이션: news/services
                         ↓
도메인·파싱: news/crawler, research/recommendation
                         ↑
인프라: Django ORM, PostgreSQL, httpx, OpenAI 호환 API
```

- `crawler`와 `research`의 핵심 규칙은 Django 모델·HTTP request/response·PostgreSQL 타입을 알지 않는다.
- 서비스는 유스케이스 흐름과 트랜잭션을 조정한다. 규칙 엔진을 서비스 하나에 새로 만들지 않는다.
- 뷰·폼·Admin·명령은 입력 검증, 권한/메시지, 서비스 호출, 출력 변환을 담당한다.
- 외부 API 응답은 서비스/어댑터 경계에서 내부 값으로 변환한다. 응답 딕셔너리를 다른 계층으로 전파하지 않는다.

## 모델과 저장소

- 현재 뉴스 저장소는 Django ORM 모델과 필요한 raw SQL로 구현되어 있다. 스키마의 단일 소유자는 Django 마이그레이션이다.
- raw SQL은 `INSERT ... ON CONFLICT`의 영향 행 수, JSONB upsert처럼 ORM만으로 현재 계약을 정확히 표현하기 어려운 지점에 한정한다. 사용 시 SQL 경계와 제약을 코드 주석·테스트로 남긴다.
- DB가 보장할 수 있는 불변식(유니크 키, 생성 열, 인덱스)은 애플리케이션 중복 검사보다 DB에 둔다.
- 새 리서치 저장소는 도메인/애플리케이션이 필요한 조회 계약을 먼저 정의하고, ORM 구현은 그 뒤에 둔다.

## 변경 규칙

1. 변경 전 관련 모델, 서비스, 파서, 테스트, 기존 문서를 확인한다.
2. 어떤 도메인 규칙·상태 전이·외부 계약이 바뀌는지 문서화한다.
3. 순수 규칙은 프레임워크 없는 테스트를 먼저 또는 함께 추가한다.
4. 마이그레이션은 `models.py` 변경으로 생성하고, 과거 migration을 수정하지 않는다.
5. 관계없는 레이어 재편이나 추상화 추가를 같은 변경에 섞지 않는다.

## 현재 예외와 해석

`news/crawler/fetcher.py`와 `body.py`는 HTTP 클라이언트를 사용한다. 이것은 URL 검증·robots·크기 제한과 파서의 결합된 수집 어댑터이며, 클라이언트를 인자로 받아 호출부가 수명을 소유한다. 이 예외는 Django·ORM 의존을 허용하는 뜻이 아니다.

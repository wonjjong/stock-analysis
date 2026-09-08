# Backend Agent 지침

## 책임

- 유스케이스, 도메인 규칙, 애그리게이트, 값 객체, 애플리케이션 서비스와 API를 구현한다.
- 뉴스 크롤러와 리서치 계산의 핵심 규칙을 프레임워크 없이 테스트 가능하게 유지한다.
- Django ORM, HTTP 클라이언트, 외부 AI/API SDK는 인프라 경계 뒤에 둔다.
- API 계약이 바뀌면 Frontend와 QA가 확인할 수 있도록 입력·출력·오류 형식을 기록한다.

## 작업 규칙

1. 먼저 관련 모델, 서비스, 파서, 테스트, 정책 문서를 읽고 현재 경계를 파악한다.
2. 도메인 개념과 불변식을 식별한 뒤, 변경이 필요한 계층을 최소 범위로 결정한다.
3. 중요한 값은 Value Object 또는 명시적인 타입으로 표현하고, 상태 변경은 객체의 행위로 캡슐화한다.
4. View/Form/Management Command에는 입출력 변환과 유스케이스 호출만 둔다.
5. Repository/외부 연동이 필요하면 포트와 어댑터를 분리하고, 외부 응답 타입을 도메인에 전파하지 않는다.
6. 스키마 변경은 새 Django migration으로만 반영하며 과거 migration은 수정하지 않는다.
7. 새 도메인 규칙에는 순수 단위 테스트를 먼저 또는 함께 추가한다.

## 완료 기준

- 관련 테스트와 전체 테스트가 통과한다.
- `backend/.venv/bin/ruff check .`가 통과한다.
- parity 동작을 변경했다면 변경 이유와 영향 범위를 설명한다.
- 변경한 API 계약, migration, 운영상 주의점을 최종 보고에 포함한다.

## 검증 명령

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

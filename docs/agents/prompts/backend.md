# Backend Agent 호출 프롬프트

아래 프롬프트를 Backend 역할 에이전트에 전달한다.

```text
너는 이 작업의 Backend Agent다. 먼저 저장소 루트의 AGENTS.md와
docs/agents/backend.md를 읽고, 관련 코드·테스트·정책 문서를 확인하라.

요청사항:
{BACKEND_TASK}

DDD와 객체지향 원칙을 적용하되 전체 구조를 불필요하게 재작성하지 말라.
도메인 규칙은 도메인 객체에 두고, 외부 연동과 Django/ORM 의존성은 경계 뒤에 둬라.
변경 전 설계 판단과 영향 범위를 짧게 정리하고, 최소 범위로 구현하라.
관련 테스트와 다음 명령을 실행하라:
cd backend && .venv/bin/python -m pytest && .venv/bin/ruff check .

최종 결과에는 변경 파일, 도메인 설계 판단, API/migration 변경, 테스트 결과,
남은 위험을 포함하라.
```

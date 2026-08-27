"""
이식 동일성 테스트의 공통 픽스처.

`tests/parity/expected.json` 은 동결된 TypeScript 구현이 고정 입력에 대해 낸 출력이다.
Python 이식판은 같은 입력에 같은 출력을 내야 한다. 이 파일이 그 정답지를 읽어 온다.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings

PARITY_PATH = Path(settings.REPO_ROOT) / "tests" / "parity" / "expected.json"


@pytest.fixture(scope="session")
def parity() -> dict:
    if not PARITY_PATH.is_file():
        pytest.fail(
            f"{PARITY_PATH} 가 없습니다. 저장소 루트에서 `node scripts/harvest-parity.mjs` 를"
            " 실행해 TypeScript 기준선을 먼저 만드세요."
        )
    return json.loads(PARITY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def now_ms(parity: dict) -> int:
    """기준선을 만들 때 쓴 고정 시점. 모든 상대 시각 계산이 이 값을 기준으로 한다."""
    return int(parity["meta"]["now"])


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 DB 스키마
#
# 스키마 소유자는 drizzle(`db/schema.ts` → `drizzle/*.sql`)이고 Django 모델은
# `managed = False` 다. 그래서 Django 가 만든 테스트 DB 는 비어 있다. Django 마이그레이션
# 대신 drizzle 이 생성한 SQL 을 그대로 적용해 실제 스키마와 일치시킨다.
#
# 부수 효과로 "drizzle 마이그레이션이 빈 DB 에 재생 가능한가"를 매 테스트 실행마다
# 검증하게 된다.
# ─────────────────────────────────────────────────────────────────────────────

DRIZZLE_DIR = Path(settings.REPO_ROOT) / "drizzle"


def _drizzle_statements() -> list[str]:
    files = sorted(DRIZZLE_DIR.glob("[0-9]*.sql"))
    if not files:
        pytest.fail(f"{DRIZZLE_DIR} 에 마이그레이션 SQL 이 없습니다.")
    statements: list[str] = []
    for path in files:
        # drizzle 은 문장 사이에 `--> statement-breakpoint` 주석을 넣는다.
        body = path.read_text(encoding="utf-8").replace("--> statement-breakpoint", "")
        # 주석 줄을 먼저 걷어낸다. 조각 단위로 `--` 시작 여부를 보면, 주석 블록 뒤에
        # 붙은 첫 문장까지 함께 버려진다(실제로 DROP DEFAULT 가 사라져 마이그레이션이
        # 깨졌다).
        body = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("--")
        )
        for chunk in body.split(";"):
            statement = chunk.strip()
            if statement:
                statements.append(statement)
    return statements


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Django 가 테스트 DB 를 만든 뒤, drizzle 스키마를 얹는다."""
    with django_db_blocker.unblock():
        from django.db import connection

        with connection.cursor() as cursor:
            for statement in _drizzle_statements():
                cursor.execute(statement)
    return django_db_setup

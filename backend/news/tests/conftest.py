"""
이식 동일성 테스트의 공통 픽스처.

`tests/parity/expected.json` 은 동결된 TypeScript 구현이 고정 입력에 대해 낸 출력이다.
Python 이식판은 같은 입력에 같은 출력을 내야 한다. 이 파일이 그 정답지를 읽어 온다.
"""

import json
from pathlib import Path

import pytest

# 정답지와 픽스처는 backend 안에 둔다. TypeScript 를 지운 뒤에는 이것이 크롤러 동작의
# 유일한 명세다.
TESTS_DIR = Path(__file__).resolve().parent
PARITY_PATH = TESTS_DIR / "parity" / "expected.json"


@pytest.fixture(scope="session")
def parity() -> dict:
    if not PARITY_PATH.is_file():
        pytest.fail(
            f"{PARITY_PATH} 가 없습니다. 이 파일은 동결된 TypeScript 구현에서 뽑은"
            " 정답지이며 크롤러 동작의 명세입니다. git 에서 복구하세요."
        )
    return json.loads(PARITY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def now_ms(parity: dict) -> int:
    """기준선을 만들 때 쓴 고정 시점. 모든 상대 시각 계산이 이 값을 기준으로 한다."""
    return int(parity["meta"]["now"])



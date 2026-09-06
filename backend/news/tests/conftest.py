"""고정 회귀 정답지의 공통 픽스처."""

import json
from pathlib import Path

import pytest

# 정답지와 픽스처는 backend 안에 둔다.
TESTS_DIR = Path(__file__).resolve().parent
PARITY_PATH = TESTS_DIR / "parity" / "expected.json"


@pytest.fixture(scope="session")
def parity() -> dict:
    if not PARITY_PATH.is_file():
        pytest.fail(
            f"{PARITY_PATH} 가 없습니다. 이 파일은 크롤러 회귀 테스트의 정답지입니다."
            " git 에서 복구하세요."
        )
    return json.loads(PARITY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def now_ms(parity: dict) -> int:
    """기준선을 만들 때 쓴 고정 시점. 모든 상대 시각 계산이 이 값을 기준으로 한다."""
    return int(parity["meta"]["now"])


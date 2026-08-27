"""
테스트 설정.

이식 단계의 테스트는 대부분 **순수 함수 동일성 검증**이라 DB가 필요 없다. DB를 쓰는
테스트만 `@pytest.mark.django_db` 를 붙인다.
"""

import os

# DATABASE_URL 이 없는 CI 에서도 설정 임포트가 실패하지 않게 한다.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:55432/signalist")

from .base import *  # noqa: F403

DEBUG = False
# 테스트 DB 이름을 분리해 개발 데이터를 건드리지 않는다.
DATABASES["default"]["TEST"] = {"NAME": "signalist_test"}  # noqa: F405

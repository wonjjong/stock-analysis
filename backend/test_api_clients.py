"""DART·SEC 연동 수동 스모크 스크립트.

pytest testpaths 밖(backend 루트)에 있어 자동으로 수집되지 않는다. 실제 네트워크를
때리므로 연동을 눈으로 확인할 때만 직접 실행한다: python test_api_clients.py
"""

import asyncio
import os
import sys
from pathlib import Path

import django

sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signalist.settings.dev")
django.setup()

from research.services import (  # noqa: E402
    CompanyIndexError,
    DartApiError,
    DartClient,
    SecApiError,
    SecClient,
    resolve_kr_company,
    resolve_us_company,
)


def test_indexes() -> None:
    print("\n[인덱스] 티커/종목코드 → 기관 식별자 해결 테스트")
    try:
        company = resolve_us_company("IREN")
        print(f"✅ SEC: IREN → CIK {company.key} ({company.name}), 기준일 {company.as_of}")
        print(f"   AAPL → CIK {resolve_us_company('AAPL').key}")
    except CompanyIndexError as reason:
        print(f"❌ SEC 인덱스 실패: {reason}")

    try:
        company = resolve_kr_company("005930")
        print(f"✅ DART: 005930 → corp_code {company.key} ({company.name}), 기준일 {company.as_of}")
        print(f"   '삼성전자' → corp_code {resolve_kr_company('삼성전자').key}")
    except CompanyIndexError as reason:
        print(f"❌ DART 인덱스 실패: {reason}")


async def test_clients() -> None:
    print("=== API 클라이언트 테스트 시작 ===")
    test_indexes()

    dart = DartClient()
    if dart.api_key:
        print("\n[DART] 테스트 중 (삼성전자 corp_code: 00126380)...")
        try:
            res = await dart.get_financial_statement(corp_code="00126380", year="2023")
            rows = res.get("list") or []
            print(f"✅ DART 성공: 주요계정 {len(rows)}건")
            for item in rows:
                if item.get("account_nm") == "영업이익":
                    print(f"   - 영업이익: {item.get('thstrm_amount')}원")
                    break
        except DartApiError as reason:
            print(f"❌ DART 실패: {reason}")
    else:
        print("\n[DART] SKIP: SIGNALIST_DART_API_KEY가 설정되지 않았습니다.")

    print("\n[SEC] 테스트 중 (Apple CIK: 0000320193)...")
    try:
        res = await SecClient().get_company_facts(cik="320193")
        print(f"✅ SEC 성공: {res.get('entityName')} 데이터를 가져왔습니다.")
        for taxonomy, concepts in (res.get("facts") or {}).items():
            print(f"   - {taxonomy}: {len(concepts)}개 개념")
    except SecApiError as reason:
        print(f"❌ SEC 실패: {reason}")

    print("\n=== 테스트 종료 ===")


if __name__ == "__main__":
    asyncio.run(test_clients())

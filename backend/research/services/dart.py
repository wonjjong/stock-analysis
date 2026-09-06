"""Open DART API 클라이언트.

corp_code 를 찾는 일은 services.dart_index 가 맡는다. 그 목록은 JSON 이 아니라 ZIP 으로
배포되어 이 클라이언트의 _request(JSON 파싱 + status 검사)를 재사용할 수 없다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"
DEFAULT_TIMEOUT = 10.0

# DART 는 성공을 '000' 으로 준다. 나머지는 모두 오류 코드다.
SUCCESS_STATUS = "000"
STATUS_MESSAGES = {
    "010": "등록되지 않은 DART API 키입니다.",
    "011": "사용할 수 없는 DART API 키입니다.",
    "013": "조회된 데이터가 없습니다.",
    "020": "DART 요청 한도를 초과했습니다.",
    "100": "DART 요청 인자가 올바르지 않습니다.",
}


class DartApiError(RuntimeError):
    """DART 요청 실패. 메시지가 화면에 그대로 노출된다."""


def describe_status(status: str, message: str = "") -> str:
    """DART 상태 코드를 사람이 읽을 수 있는 한국어 메시지로 바꾼다."""
    known = STATUS_MESSAGES.get(status)
    if known and message:
        return f"{known} ({status}: {message})"
    if known:
        return f"{known} ({status})"
    return f"DART 요청이 실패했습니다({status}): {message}"


class DartClient:
    """
    Open DART API 클라이언트.
    공시 검색 및 주요 재무 사항을 가져오는 기능을 제공합니다.
    """

    BASE_URL = BASE_URL

    def __init__(self, api_key: str | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key or getattr(settings, "SIGNALIST_DART_API_KEY", "")
        if not self.api_key:
            logger.warning("DART API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        self.timeout = timeout

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise DartApiError("DART API 키가 없습니다. SIGNALIST_DART_API_KEY 를 설정하세요.")

        url = f"{self.BASE_URL}/{endpoint}"
        params = {**params, "crtfc_key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as reason:
            logger.warning("DART 요청 실패 (%s): %s", url, reason)
            raise DartApiError(f"DART 에 연결하지 못했습니다: {reason}") from reason
        except ValueError as reason:
            raise DartApiError(f"DART 응답을 JSON 으로 읽지 못했습니다: {endpoint}") from reason

        status = str(data.get("status", ""))
        if status != SUCCESS_STATUS:
            message = describe_status(status, str(data.get("message", "")))
            logger.warning("DART 응답 오류 (%s): %s", url, message)
            raise DartApiError(message)
        return data

    async def get_financial_statement(
        self, corp_code: str, year: str, reprt_code: str = "11011"
    ) -> dict[str, Any]:
        """
        단일회사 주요계정 가져오기
        reprt_code: 11013(1분기), 11012(반기), 11014(3분기), 11011(사업보고서)
        """
        params = {"corp_code": corp_code, "bsns_year": year, "reprt_code": reprt_code}
        return await self._request("fnlttSinglAcnt.json", params)

    async def get_multi_financial_statement(
        self, corp_codes: list[str], year: str, reprt_code: str = "11011"
    ) -> dict[str, Any]:
        """다중회사 주요계정 가져오기 (최대 100건)"""
        params = {
            "corp_code": ",".join(corp_codes),
            "bsns_year": year,
            "reprt_code": reprt_code,
        }
        return await self._request("fnlttMultiAcnt.json", params)

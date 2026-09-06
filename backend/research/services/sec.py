"""SEC EDGAR API 클라이언트.

## Host 헤더를 직접 넣지 않는다
httpx 가 URL 에서 Host 를 설정한다. 예전 코드는 헤더에 Host: data.sec.gov 를 박아
두었는데, 그러면 티커 목록이 사는 www.sec.gov 에 같은 클라이언트를 쓸 수 없다.

## User-Agent 가 없으면 SEC 가 거절한다
UA 를 비우고 요청하면 403 "Undeclared Automated Tool" 이 온다. 설정이 비어 있어도
식별 가능한 기본값을 채워 당장은 동작하게 하되, 운영자가 고치도록 경고는 남긴다.

## 실패를 빈 dict 로 감추지 않는다
예전 코드는 어떤 예외든 {} 를 돌려줬다. 그러면 "UA 미설정으로 403" 과 "자료가 없는
회사" 가 호출부에서 같아 보인다. market_data.MarketDataError 관례에 맞춰 예외를 던지고,
근거를 붙이지 못하는 것 자체는 상위에서 흡수한다.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

from research.services.rate_limit import SEC_GATE

logger = logging.getLogger(__name__)

DATA_BASE_URL = "https://data.sec.gov"
WWW_BASE_URL = "https://www.sec.gov"

# SEC 는 '이름 이메일' 형식을 요구한다. 미설정이어도 익명 UA 보다는 식별 가능한 편이 낫다.
FALLBACK_USER_AGENT = "Signalist Research Bot (contact-not-configured@example.invalid)"

DEFAULT_TIMEOUT = 15.0


class SecApiError(RuntimeError):
    """SEC 요청 실패. 메시지가 화면에 그대로 노출된다."""


def build_user_agent(configured: str | None = None) -> str:
    """설정된 User-Agent 를 돌려준다. 비어 있으면 경고 후 기본값을 쓴다."""
    user_agent = (configured or getattr(settings, "SIGNALIST_SEC_USER_AGENT", "") or "").strip()
    if user_agent:
        return user_agent
    logger.warning(
        "SIGNALIST_SEC_USER_AGENT 가 비어 있습니다. SEC 는 '이름 이메일' 형식의 "
        "User-Agent 를 요구하므로 .env 에 설정하세요."
    )
    return FALLBACK_USER_AGENT


def sec_headers(user_agent: str | None = None) -> dict[str, str]:
    """SEC 요청 공통 헤더. Host 는 넣지 않는다(httpx 가 URL 에서 설정한다)."""
    return {
        "User-Agent": build_user_agent(user_agent),
        "Accept-Encoding": "gzip, deflate",
    }


def describe_status(status_code: int, context: str) -> str:
    """SEC 응답 코드를 사람이 읽을 수 있는 한국어 메시지로 바꾼다."""
    if status_code == 403:
        return (
            "SEC 가 요청을 거부했습니다(403). SIGNALIST_SEC_USER_AGENT 를 "
            "'이름 이메일' 형식으로 설정했는지 확인하세요."
        )
    if status_code == 404:
        return f"SEC 에 {context} 자료가 없습니다(404)."
    if status_code == 429:
        return "SEC 요청 한도를 초과했습니다(429). 잠시 후 다시 시도하세요."
    return f"SEC 요청이 실패했습니다({status_code}): {context}"


class SecClient:
    """SEC EDGAR 의 CIK 기반 공시·재무 엔드포인트를 호출한다.

    티커로 CIK 를 찾는 일은 services.sec_index 가 맡는다. 그 파일은 호스트가 다르고
    (www.sec.gov) 응답 수명도 달라서 이 클라이언트와 책임을 분리했다.
    """

    BASE_URL = DATA_BASE_URL

    def __init__(self, user_agent: str | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.headers = sec_headers(user_agent)
        self.user_agent = self.headers["User-Agent"]
        self.timeout = timeout

    async def _request(self, endpoint: str) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        await SEC_GATE.await_slot()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
        except httpx.HTTPError as reason:
            logger.warning("SEC 요청 실패 (%s): %s", url, reason)
            raise SecApiError(f"SEC 에 연결하지 못했습니다: {reason}") from reason

        if response.status_code >= 400:
            message = describe_status(response.status_code, endpoint)
            logger.warning("SEC 응답 오류 (%s): %s", url, response.status_code)
            raise SecApiError(message)

        try:
            return response.json()
        except ValueError as reason:
            raise SecApiError(f"SEC 응답을 JSON 으로 읽지 못했습니다: {endpoint}") from reason

    async def get_company_submissions(self, cik: str) -> dict[str, Any]:
        """회사의 최근 공시 목록 가져오기"""
        return await self._request(f"submissions/CIK{cik.zfill(10)}.json")

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        """회사의 모든 XBRL 팩트 데이터 가져오기"""
        return await self._request(f"api/xbrl/companyfacts/CIK{cik.zfill(10)}.json")

    async def get_company_concept(self, cik: str, taxonomy: str, concept: str) -> dict[str, Any]:
        """
        특정 회계 개념(NetIncomeLoss 등)에 대한 시계열 데이터 가져오기
        예: cik='320193', taxonomy='us-gaap', concept='NetIncomeLoss'
        """
        endpoint = f"api/xbrl/companyconcept/CIK{cik.zfill(10)}/{taxonomy}/{concept}.json"
        return await self._request(endpoint)

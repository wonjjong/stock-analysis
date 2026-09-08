"""공시 어댑터를 분석 유스케이스가 쓸 수 있는 컨텍스트로 조립한다."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from research.analysis import Evidence
from research.dart_profile import account_evidence, fundamentals_from_accounts, parse_single_account
from research.fundamentals import FundamentalMetrics
from research.sec_profile import (
    build_filer_profile,
    financial_evidence,
    fundamentals_from_company_facts,
    profile_evidence,
)
from research.symbols import SymbolRoute

from .company_index import CompanyIndexError
from .dart import DartApiError, DartClient
from .dart_index import resolve_kr_company
from .sec import SecApiError, SecClient
from .sec_index import resolve_us_company

logger = logging.getLogger(__name__)

DART_ANNUAL_REPORT = "11011"


@dataclass(frozen=True, slots=True)
class FilingContext:
    """공시 근거와, 정량 점수에 반영할 수 있는 재무 입력값."""

    evidence: tuple[Evidence, ...] = ()
    fundamentals: FundamentalMetrics | None = None


async def fetch_dart_fundamentals(
    route: SymbolRoute, market_cap: float | None
) -> FundamentalMetrics | None:
    """한국 종목의 DART 사업보고서를 팩터 입력값으로 읽는다.

    공시는 보조 데이터이므로 API·인덱스 실패가 시세 기반 분석 전체를 중단시키지 않는다.
    """
    if route.market != "KR":
        return None


async def fetch_filing_fundamentals(
    route: SymbolRoute, market_cap: float | None
) -> FundamentalMetrics | None:
    """시장별 공시를 같은 FundamentalMetrics로 변환하는 단일 진입점."""
    if route.market == "KR":
        return await fetch_dart_fundamentals(route, market_cap)
    try:
        company = resolve_us_company(route.base)
        facts = await SecClient().get_company_facts(company.key)
        return fundamentals_from_company_facts(facts, market_cap=market_cap)
    except (CompanyIndexError, SecApiError) as reason:
        logger.info("SEC 재무 점수를 읽지 못했습니다 (%s): %s", route.symbol, reason)
        return None
    year = str(datetime.now(UTC).year - 1)
    try:
        company = resolve_kr_company(route.base)
        payload = await DartClient().get_financial_statement(
            corp_code=company.key, year=year, reprt_code=DART_ANNUAL_REPORT
        )
        return fundamentals_from_accounts(
            parse_single_account(payload), year=year, market_cap=market_cap
        )
    except (CompanyIndexError, DartApiError) as reason:
        logger.info("DART 재무 점수를 읽지 못했습니다 (%s): %s", route.symbol, reason)
        return None


async def fetch_filing_context(route: SymbolRoute, market_cap: float | None) -> FilingContext:
    """AI 분석에 보일 공시 근거와 한국 종목의 DART 재무 팩터를 가져온다."""
    available_at = datetime.now(UTC).isoformat()
    if route.market == "KR":
        year = str(datetime.now(UTC).year - 1)
        try:
            company = resolve_kr_company(route.base)
            payload = await DartClient().get_financial_statement(
                corp_code=company.key, year=year, reprt_code=DART_ANNUAL_REPORT
            )
            accounts = parse_single_account(payload)
            return FilingContext(
                evidence=tuple(
                    account_evidence(company, accounts, year, DART_ANNUAL_REPORT, available_at)
                ),
                fundamentals=fundamentals_from_accounts(
                    accounts, year=year, market_cap=market_cap
                ),
            )
        except (CompanyIndexError, DartApiError) as reason:
            logger.info("DART 공시 근거를 붙이지 못했습니다 (%s): %s", route.symbol, reason)
            return FilingContext()

    try:
        company = resolve_us_company(route.base)
        submissions = await SecClient().get_company_submissions(company.key)
        facts = await SecClient().get_company_facts(company.key)
        fundamentals = fundamentals_from_company_facts(facts, market_cap=market_cap)
        evidence = list(profile_evidence(build_filer_profile(submissions), available_at))
        if fundamentals is not None:
            evidence.append(financial_evidence(fundamentals, available_at))
        return FilingContext(
            evidence=tuple(evidence),
            fundamentals=fundamentals,
        )
    except (CompanyIndexError, SecApiError) as reason:
        logger.info("SEC 공시 근거를 붙이지 못했습니다 (%s): %s", route.symbol, reason)
        return FilingContext()

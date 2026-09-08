"""DART 주요계정(fnlttSinglAcnt) 응답을 재무 근거로 바꾼다. sec_profile 과 대칭이다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.analysis import Evidence
from research.fundamentals import FundamentalMetrics
from research.services.company_index import CompanyRef

REPRT_CODES = {
    "11011": "사업보고서",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}
# 연결(CFS)이 있으면 우선 쓰고, 없으면 개별(OFS)로 떨어진다.
PREFERRED_FS = ("CFS", "OFS")
KEY_ACCOUNTS = ("매출액", "영업이익", "당기순이익", "자산총계", "부채총계", "자본총계")


@dataclass(frozen=True, slots=True)
class DartAccount:
    account_name: str
    fs_div: str
    current: float | None
    previous: float | None


def _amount(value: object) -> float | None:
    """DART 금액 문자열을 float 로. 콤마·공백·'-'(값 없음)를 안전하게 처리한다."""
    text = str(value or "").replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_single_account(payload: dict[str, Any]) -> tuple[DartAccount, ...]:
    """주요계정 응답의 list 를 파싱한다. 순수 함수라 테스트가 여기를 직접 친다."""
    return tuple(
        DartAccount(
            account_name=str(row.get("account_nm") or "").strip(),
            fs_div=str(row.get("fs_div") or "").strip().upper(),
            current=_amount(row.get("thstrm_amount")),
            previous=_amount(row.get("frmtrm_amount")),
        )
        for row in payload.get("list") or ()
        if isinstance(row, dict)
    )


def select_accounts(accounts: tuple[DartAccount, ...]) -> dict[str, DartAccount]:
    """계정명별로 하나씩 고른다. 연결 재무제표를 개별보다 우선한다."""
    chosen: dict[str, DartAccount] = {}
    for division in PREFERRED_FS:
        for account in accounts:
            if account.fs_div == division and account.account_name not in chosen:
                chosen[account.account_name] = account
    for account in accounts:
        chosen.setdefault(account.account_name, account)
    return chosen


def fundamentals_from_accounts(
    accounts: tuple[DartAccount, ...], *, year: str, market_cap: float | None
) -> FundamentalMetrics | None:
    """DART 주요계정을 가치·퀄리티 팩터 입력으로 변환한다.

    손익·자본은 연결재무제표를 우선한 ``select_accounts`` 결과를 쓴다. 적자와 자본잠식의
    PER/PBR은 저평가로 오인하면 안 되므로 결측으로 남겨 보조 공급자가 채우게 한다.
    """
    selected = select_accounts(accounts)
    revenue = selected.get("매출액")
    net_income = selected.get("당기순이익")
    equity = selected.get("자본총계")

    revenue_current = revenue.current if revenue else None
    revenue_previous = revenue.previous if revenue else None
    net_income_current = net_income.current if net_income else None
    equity_current = equity.current if equity else None

    revenue_growth = (
        (revenue_current / revenue_previous - 1) * 100
        if revenue_current is not None and revenue_previous not in (None, 0)
        else None
    )
    profit_margin = (
        net_income_current / revenue_current * 100
        if net_income_current is not None and revenue_current not in (None, 0)
        else None
    )
    trailing_pe = (
        market_cap / net_income_current
        if market_cap is not None
        and market_cap > 0
        and net_income_current is not None
        and net_income_current > 0
        else None
    )
    price_to_book = (
        market_cap / equity_current
        if market_cap is not None and market_cap > 0 and equity_current is not None and equity_current > 0
        else None
    )
    metrics = FundamentalMetrics(
        source="DART",
        period=f"{year}-12-31",
        trailing_pe=trailing_pe,
        price_to_book=price_to_book,
        profit_margin_pct=profit_margin,
        revenue_growth_pct=revenue_growth,
    )
    return metrics if metrics.score_inputs() else None


def account_evidence(
    company: CompanyRef,
    accounts: tuple[DartAccount, ...],
    year: str,
    reprt_code: str,
    available_at: str,
) -> list[Evidence]:
    """주요계정을 Evidence 로 바꾼다. id 접두사는 'dart:'."""
    if not accounts:
        return []
    selected = select_accounts(accounts)
    parts = [
        f"{name}={selected[name].current:,.0f}원"
        for name in KEY_ACCOUNTS
        if name in selected and selected[name].current is not None
    ]
    report_name = REPRT_CODES.get(reprt_code, reprt_code)
    return [
        Evidence(
            id=f"dart:accounts:{company.key}:{year}:{reprt_code}",
            kind="financial",
            title=f"{company.name} {year} {report_name} 주요계정",
            source="DART",
            # 사업연도 말이 사건 시점, 조회 시각이 알게 된 시점이다.
            observed_at=f"{year}-12-31",
            available_at=available_at,
            summary="; ".join(parts) or "주요계정 값을 읽지 못함",
        )
    ]

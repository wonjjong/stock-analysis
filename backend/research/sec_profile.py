"""SEC 응답을 발행사 프로필·재무 팩터·AI 입력 근거로 바꾼다.

companyfacts 는 us-gaap와 ifrs-full이 섞일 수 있다. 그래서 특정 taxonomy 하나를 전제하지
않고, 공통 의미의 개념 후보를 순서대로 찾은 뒤 연차보고서(10-K·20-F·40-F) 값만 쓴다.
개념을 찾지 못하면 0점으로 지어내지 않고 결측으로 남긴다.

## 기준일을 둘로 나눈다
공시는 사건 시점(periodOfReport)과 알 수 있게 된 시점(filingDate)이 다르다. 이 프로젝트의
PIT 규율대로 observed_at/available_at 에 각각 넣는다. yfinance 재무는 기준일이 흐릿한데
SEC 는 filingDate 가 명확하다는 것이 공시 근거를 붙이는 가장 큰 이득이다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from research.analysis import Evidence
from research.fundamentals import FundamentalMetrics

# 연차 보고서: 미국 내국법인 10-K, 미국 기준 외국법인(FPI) 20-F, 캐나다 MJDS 40-F
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"})
# 미국 기준 외국법인(FPI) 양식. 10-Q 의무가 없고 6-K 로 수시 보고한다.
FOREIGN_FORMS = frozenset({"20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A"})
DOMESTIC_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})

# 라벨에 '국내/외국' 만 쓰면 읽는 사람 기준이 흔들린다(한국 사용자에게 국내는 코스피다).
# 어느 나라 기준인지 문구에 못 박는다. 여기서 말하는 내국/외국은 언제나 **미국 기준**이다.
DOMESTIC_REGIME = "미국 내국법인 양식(10-K·10-Q)"
FOREIGN_REGIME = "미국 기준 외국법인 양식(20-F)"
FOREIGN_CURRENT_REGIME = "미국 기준 외국법인 양식(6-K 중심)"
UNKNOWN_REGIME = "미상"

# SEC stateOfIncorporation 은 미국이면 주/속령 약어, 그 밖이면 'C3'(호주) 같은 코드다.
US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
    "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "PR", "VI", "GU", "AS", "MP", "X1",
})

ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

REVENUE_CONCEPTS = (
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "Revenues"),
    ("ifrs-full", "Revenue"),
)
NET_INCOME_CONCEPTS = (
    ("us-gaap", "NetIncomeLoss"),
    ("ifrs-full", "ProfitLoss"),
)
EQUITY_CONCEPTS = (
    ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ("us-gaap", "StockholdersEquity"),
    ("ifrs-full", "Equity"),
)


@dataclass(frozen=True, slots=True)
class AnnualFact:
    value: float
    period: str
    filed_at: str


@dataclass(frozen=True, slots=True)
class Filing:
    form: str
    filed_at: str
    period_of_report: str
    accession: str
    url: str


@dataclass(frozen=True, slots=True)
class FilerProfile:
    """공시 이력에서 읽어 낸 발행사 성격."""

    cik: str
    entity_name: str
    tickers: tuple[str, ...]
    exchanges: tuple[str, ...]
    sic_description: str
    state_of_incorporation: str
    fiscal_year_end: str
    reporting_regime: str
    is_non_us_incorporated: bool
    previous_regime: str
    form_counts: dict[str, int]
    recent_filings: tuple[Filing, ...]
    latest_annual: Filing | None

    @property
    def files_foreign_forms(self) -> bool:
        """20-F/6-K 체계로 보고하는가. 분기 실적을 기대할 수 있는지가 여기에 달렸다."""
        return self.reporting_regime.startswith("미국 기준 외국법인")

    @property
    def changed_regime(self) -> bool:
        """보고 양식을 갈아탔는가. 갈아탔다면 과거 XBRL taxonomy 도 함께 바뀌었을 수 있다."""
        return self.previous_regime not in (UNKNOWN_REGIME, self.reporting_regime)


def _annual_facts(payload: dict[str, Any], concepts: tuple[tuple[str, str], ...]) -> tuple[AnnualFact, ...]:
    """동일 개념·통화 단위의 연차 팩트를 최신 순으로 찾는다."""
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return ()
    for taxonomy, concept in concepts:
        concepts_by_name = facts.get(taxonomy)
        if not isinstance(concepts_by_name, dict):
            continue
        raw_concept = concepts_by_name.get(concept)
        if not isinstance(raw_concept, dict):
            continue
        units = raw_concept.get("units")
        if not isinstance(units, dict):
            continue
        for rows in units.values():
            if not isinstance(rows, list):
                continue
            result: dict[str, AnnualFact] = {}
            for row in rows:
                if not isinstance(row, dict) or str(row.get("form") or "") not in ANNUAL_FORMS:
                    continue
                try:
                    value = float(row["val"])
                except (KeyError, TypeError, ValueError):
                    continue
                period = str(row.get("end") or "")
                filed_at = str(row.get("filed") or "")
                if not period or not filed_at:
                    continue
                previous = result.get(period)
                if previous is None or filed_at > previous.filed_at:
                    result[period] = AnnualFact(value=value, period=period, filed_at=filed_at)
            if result:
                return tuple(sorted(result.values(), key=lambda item: item.period, reverse=True))
    return ()


def fundamentals_from_company_facts(
    payload: dict[str, Any], *, market_cap: float | None
) -> FundamentalMetrics | None:
    """SEC companyfacts의 최근 연차 재무제표를 공통 팩터 입력값으로 정규화한다."""
    revenues = _annual_facts(payload, REVENUE_CONCEPTS)
    incomes = _annual_facts(payload, NET_INCOME_CONCEPTS)
    equities = _annual_facts(payload, EQUITY_CONCEPTS)
    current_revenue = revenues[0] if revenues else None
    previous_revenue = revenues[1] if len(revenues) > 1 else None
    current_income = next(
        (item for item in incomes if current_revenue is not None and item.period == current_revenue.period),
        incomes[0] if incomes else None,
    )
    current_equity = next(
        (item for item in equities if current_revenue is not None and item.period == current_revenue.period),
        equities[0] if equities else None,
    )

    revenue_growth = (
        (current_revenue.value / previous_revenue.value - 1) * 100
        if current_revenue is not None and previous_revenue is not None and previous_revenue.value != 0
        else None
    )
    profit_margin = (
        current_income.value / current_revenue.value * 100
        if current_income is not None and current_revenue is not None and current_revenue.value != 0
        else None
    )
    trailing_pe = (
        market_cap / current_income.value
        if market_cap is not None
        and market_cap > 0
        and current_income is not None
        and current_income.value > 0
        else None
    )
    price_to_book = (
        market_cap / current_equity.value
        if market_cap is not None
        and market_cap > 0
        and current_equity is not None
        and current_equity.value > 0
        else None
    )
    period = current_revenue.period if current_revenue is not None else ""
    metrics = FundamentalMetrics(
        source="SEC EDGAR",
        period=period,
        trailing_pe=trailing_pe,
        price_to_book=price_to_book,
        profit_margin_pct=profit_margin,
        revenue_growth_pct=revenue_growth,
    )
    return metrics if metrics.score_inputs() else None


def financial_evidence(metrics: FundamentalMetrics, available_at: str) -> Evidence:
    """수치화된 SEC 재무제표가 AI 근거 목록에서도 보이게 한다."""
    parts = [
        f"매출성장률 {metrics.revenue_growth_pct:.1f}%"
        if metrics.revenue_growth_pct is not None
        else "",
        f"순이익률 {metrics.profit_margin_pct:.1f}%" if metrics.profit_margin_pct is not None else "",
        f"PER {metrics.trailing_pe:.1f}" if metrics.trailing_pe is not None else "",
        f"PBR {metrics.price_to_book:.1f}" if metrics.price_to_book is not None else "",
    ]
    return Evidence(
        id=f"sec:annual-financials:{metrics.period}",
        kind="financial",
        title=f"SEC EDGAR {metrics.period} 연차 재무 팩터",
        source="SEC EDGAR",
        observed_at=metrics.period,
        available_at=available_at,
        summary="; ".join(part for part in parts if part),
    )


def _classify_regime(forms: set[str]) -> str:
    """어떤 보고 양식을 쓰는지 판정한다. **국적이 아니라 양식**이다.

    호주 법인 IREN 처럼 미국 밖 회사가 FPI 지위를 벗고 10-K/10-Q 로 보고하는 경우가 있어,
    설립지는 is_non_us_incorporated 로 따로 노출한다.
    """
    if forms & DOMESTIC_FORMS:
        return DOMESTIC_REGIME
    if forms & {"20-F", "20-F/A", "40-F", "40-F/A"}:
        return FOREIGN_REGIME
    if forms & {"6-K", "6-K/A"}:
        return FOREIGN_CURRENT_REGIME
    return UNKNOWN_REGIME


def _filing_url(cik: str, accession: str, document: str) -> str:
    if not accession:
        return ""
    plain = accession.replace("-", "")
    tail = f"/{document}" if document else ""
    return f"{ARCHIVE_BASE}/{cik.lstrip('0')}/{plain}{tail}"


def build_filer_profile(submissions: dict[str, Any], limit: int = 20) -> FilerProfile:
    """submissions JSON 을 FilerProfile 로 바꾼다. 네트워크가 없는 순수 함수다."""
    cik = str(submissions.get("cik") or "").zfill(10)
    state = str(submissions.get("stateOfIncorporation") or "").strip().upper()
    recent = (submissions.get("filings") or {}).get("recent") or {}

    # filings.recent 는 열 지향(각 키가 같은 길이의 배열)이라 행으로 전치해야 한다.
    columns = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    series = [recent.get(name) or [] for name in columns]
    rows = list(zip(*series, strict=False)) if all(isinstance(item, list) for item in series) else []

    filings = tuple(
        Filing(
            form=str(form),
            filed_at=str(filed),
            period_of_report=str(report or filed),
            accession=str(accession),
            url=_filing_url(cik, str(accession), str(document)),
        )
        for form, filed, report, accession, document in rows
    )
    form_counts = dict(Counter(item.form for item in filings).most_common())
    latest_annual = next((item for item in filings if item.form in ANNUAL_FORMS), None)

    return FilerProfile(
        cik=cik,
        entity_name=str(submissions.get("name") or ""),
        tickers=tuple(str(item) for item in submissions.get("tickers") or ()),
        exchanges=tuple(str(item) for item in submissions.get("exchanges") or ()),
        sic_description=str(submissions.get("sicDescription") or ""),
        state_of_incorporation=state,
        fiscal_year_end=str(submissions.get("fiscalYearEnd") or ""),
        reporting_regime=_classify_regime({item.form for item in filings[:limit]}),
        is_non_us_incorporated=bool(state) and state not in US_STATE_CODES,
        # recent 의 뒤쪽(오래된 공시)으로 예전 양식을 본다. 20-F → 10-K 전환을 잡아낸다.
        previous_regime=_classify_regime({item.form for item in filings[-limit:]}),
        form_counts=form_counts,
        recent_filings=filings[:limit],
        latest_annual=latest_annual,
    )


def profile_evidence(profile: FilerProfile, available_at: str, limit: int = 5) -> list[Evidence]:
    """FilerProfile 을 Evidence 로 바꾼다. id 접두사는 'sec:'."""
    incorporation = profile.state_of_incorporation or "미상"
    if profile.is_non_us_incorporated:
        incorporation += "(미국 밖)"
    identity = (
        f"CIK {profile.cik}; 사명 {profile.entity_name}; 거래소 {', '.join(profile.exchanges) or '미상'}; "
        f"업종 {profile.sic_description or '미상'}; 설립지 {incorporation}; "
        f"결산월 {profile.fiscal_year_end or '미상'}; 보고 양식 {profile.reporting_regime}."
    )
    if profile.files_foreign_forms:
        identity += " 이 양식은 분기 실적 공시 의무가 없어 10-Q 가 존재하지 않는다."
    if profile.changed_regime:
        # 양식 전환은 XBRL taxonomy 전환(ifrs-full → us-gaap)을 동반하는 일이 많아,
        # 과거 재무를 한 체계로만 읽으면 그 구간이 비어 보인다.
        identity += (
            f" 과거에는 {profile.previous_regime} 으로 보고했다. 보고 체계가 바뀐 구간은"
            " 회계기준(IFRS/US-GAAP)도 함께 바뀌었을 수 있다."
        )
    if profile.is_non_us_incorporated and not profile.files_foreign_forms:
        identity += " 미국 밖에서 설립된 법인이지만 미국 내국법인 양식으로 보고한다."

    mix = ", ".join(f"{form} {count}건" for form, count in list(profile.form_counts.items())[:8])
    # 프로필 자체에는 고유한 사건 시점이 없다. 연차보고서 기준일을 쓰되, 펀드처럼 연차
    # 보고서를 내지 않는 발행사는 가장 최근 공시의 보고기준일로 떨어진다.
    anchor = profile.latest_annual or (profile.recent_filings[0] if profile.recent_filings else None)
    observed_at = anchor.period_of_report if anchor else available_at

    evidence = [
        Evidence(
            id="sec:profile",
            kind="filing",
            title=f"{profile.entity_name or profile.cik} SEC 발행사 프로필",
            source="SEC EDGAR",
            observed_at=observed_at,
            available_at=available_at,
            summary=identity,
        ),
        Evidence(
            id="sec:filings-mix",
            kind="filing",
            title=f"{profile.entity_name or profile.cik} 최근 공시 구성",
            source="SEC EDGAR",
            observed_at=observed_at,
            available_at=available_at,
            summary=f"최근 공시 폼 분포: {mix or '없음'}.",
        ),
    ]
    for filing in profile.recent_filings[:limit]:
        evidence.append(
            Evidence(
                id=f"sec:filing:{filing.accession}",
                kind="filing",
                title=f"{filing.form} ({filing.period_of_report} 기준)",
                source="SEC EDGAR",
                observed_at=filing.period_of_report,
                available_at=filing.filed_at,
                summary=f"{profile.entity_name} 가 {filing.filed_at} 에 제출한 {filing.form}.",
                url=filing.url,
            )
        )
    return evidence

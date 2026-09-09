"""재무·기술 지표의 계산과 설명 계약. 외부 공급자와 프레임워크에 의존하지 않는다."""

# ruff: noqa: RUF001 -- 사용자에게 표시하는 수식의 곱셈·뺄셈 기호.

from __future__ import annotations

import math

from research.fundamentals import FundamentalMetrics


def finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def ratio(numerator, denominator, scale=1.0):
    top, bottom = finite(numerator), finite(denominator)
    return finite(top / bottom * scale) if top is not None and bottom is not None and bottom > 0 else None


def build_indicators(snapshot: dict, fundamentals: FundamentalMetrics | None = None) -> dict:
    details = snapshot.get("financial_details") or {}
    technical = snapshot.get("technical") or {}
    currency = snapshot.get("currency") or ""
    same_currency = bool(currency and currency == details.get("financialCurrency"))
    groups = []
    observed = snapshot.get("observed_at") or "기준일 미제공"

    def metric(
        key,
        label,
        value,
        unit,
        description,
        formula,
        *,
        period=observed,
        source="Yahoo Finance",
        reason="공급자 값 또는 계산에 필요한 이력이 없습니다.",
    ):
        return dict(
            key=key,
            label=label,
            value=finite(value),
            unit=unit,
            description=description,
            formula=formula,
            source=source,
            period=period,
            missing_reason=reason if finite(value) is None else "",
        )

    def missing_reason(key):
        """표시용 결측 사유를 지표별 원천값에 맞춰 설명한다."""
        if key == "trailing_pe":
            if fundamentals is not None:
                if finite(snapshot.get("market_cap")) in (None, 0) or finite(snapshot.get("market_cap")) < 0:
                    return "시가총액이 없거나 0 이하라 공시 기준 PER을 계산할 수 없습니다."
                if finite(snapshot.get("net_income")) is not None and finite(snapshot.get("net_income")) <= 0:
                    return "최근 연간 순이익이 0 이하라 PER을 계산하지 않습니다."
                return f"{fundamentals.source}에 PER 계산에 필요한 최근 연간 순이익이 없습니다."
            eps = finite(details.get("trailingEps"))
            if eps is not None and eps <= 0:
                return "최근 12개월 EPS가 0 이하라 PER을 계산하지 않습니다."
            if finite(snapshot.get("market_cap")) in (None, 0) or finite(snapshot.get("market_cap")) < 0:
                return "시가총액이 없거나 0 이하라 PER을 계산할 수 없습니다."
            return "Yahoo Finance가 최근 12개월 PER을 제공하지 않았습니다."
        if key == "forward_pe":
            return "Yahoo Finance가 예상 EPS 또는 예상 PER(forwardPE)을 제공하지 않았습니다."
        if key == "price_to_book":
            return "양수 자기자본·BPS 또는 공급자 PBR이 없어 비교할 수 없습니다."
        return "양수 이익·자본 또는 공급자 비율이 없어 비교가 어렵습니다."

    def provided(key, label, description, formula, unit="배", detail_key=None, scale=1):
        value = details.get(detail_key) if detail_key else snapshot.get(key)
        source, period = "Yahoo Finance · 제공 비율", "공급자 기준 · 재무 기준일 미제공"
        if fundamentals and getattr(fundamentals, key, None) is not None:
            value = getattr(fundamentals, key)
            source, period = fundamentals.source, fundamentals.period
        value = finite(value)
        if value is not None:
            value *= scale
        if unit == "배" and key in {"trailing_pe", "forward_pe", "price_to_book", "ev_ebitda"}:
            value = value if value is not None and value > 0 else None
        return metric(
            key,
            label,
            value,
            unit,
            description,
            formula,
            source=source,
            period=period,
            reason=missing_reason(key),
        )

    valuation = [
        provided(
            "trailing_pe",
            "PER · 실적",
            "이익 대비 주가 수준. 낮다고 항상 저평가는 아니며 적자 기업에는 부적합합니다.",
            "주가 ÷ 주당순이익(EPS). 공시 비율은 연간, Yahoo 값은 TTM 기준.",
        ),
        provided(
            "forward_pe",
            "PER · 예상",
            "공급자의 예상 이익을 쓴 배수. 추정치가 바뀔 수 있으며 증권사 목표가가 아닙니다.",
            "주가 ÷ 예상 EPS",
            detail_key="forwardPE",
        ),
        provided(
            "price_to_book",
            "PBR",
            "장부상 자기자본 대비 주가. 업종과 자산의 질에 따라 해석이 달라집니다.",
            "주가 ÷ 주당순자산(BPS)",
        ),
        provided(
            "ev_ebitda",
            "EV/EBITDA",
            "기업가치를 이자·세금·감가상각 전 이익과 비교합니다. 금융업에는 적합하지 않을 수 있습니다.",
            "기업가치(EV) ÷ EBITDA · 공급자 제공 비율",
            detail_key="enterpriseToEbitda",
        ),
        metric(
            "eps",
            "EPS · TTM",
            details.get("trailingEps"),
            details.get("financialCurrency") or "통화 미제공",
            "최근 12개월 주당순이익입니다. 희석주식수와 일회성 손익에 영향을 받습니다.",
            "주주귀속 순이익 ÷ 가중평균 주식수",
            period="TTM · 종료일 미제공",
        ),
        metric(
            "bps",
            "BPS",
            details.get("bookValue"),
            details.get("financialCurrency") or "통화 미제공",
            "보통주 한 주에 해당하는 장부상 순자산입니다.",
            "보통주 자기자본 ÷ 주식수",
            period="공급자 기준 · 결산일 미제공",
        ),
    ]
    quality = [
        provided(
            "roe",
            "ROE",
            "자기자본으로 얼마나 이익을 냈는지 보여줍니다. 부채 증가로 높아질 수도 있습니다.",
            "순이익 ÷ 평균 자기자본 × 100",
            "%",
            "returnOnEquity",
            100,
        ),
        provided(
            "roa",
            "ROA",
            "전체 자산 대비 수익성입니다. 자산이 많이 필요한 업종과 단순 비교하면 안 됩니다.",
            "순이익 ÷ 평균 총자산 × 100",
            "%",
            "returnOnAssets",
            100,
        ),
        provided(
            "operating_margin",
            "영업이익률",
            "본업 매출에서 영업이익으로 남은 비율입니다.",
            "영업이익 ÷ 매출 × 100",
            "%",
            "operatingMargins",
            100,
        ),
        provided(
            "profit_margin_pct",
            "순이익률",
            "매출 대비 최종 순이익. 일회성 손익과 세금의 영향을 받습니다.",
            "순이익 ÷ 매출 × 100",
            "%",
        ),
        provided(
            "revenue_growth_pct",
            "매출 성장률",
            "비교 기간 대비 매출 증가율입니다. 공급자와 공시의 비교 기간이 다를 수 있습니다.",
            "(당기 매출 ÷ 비교기 매출 − 1) × 100",
            "%",
        ),
    ]
    ocf, capex = finite(details.get("ocf")), finite(details.get("capex"))
    cash, debt = finite(details.get("cash")), finite(details.get("debt"))
    fcf = (
        ocf - abs(capex)
        if ocf is not None and capex is not None and details.get("ocf_period") == details.get("capex_period")
        else None
    )
    net_debt = debt - cash if debt is not None and cash is not None else None
    cash_period = details.get("ocf_period") or "결산일 미제공"
    balance_period = details.get("debt_period") or "결산일 미제공"
    financial_unit = details.get("financialCurrency") or "통화 미제공"
    cash_metrics = [
        metric(
            "fcf",
            "잉여현금흐름 · 단순 FCF",
            fcf,
            financial_unit,
            "영업 현금에서 설비투자를 차감한 값. 순차입을 포함한 FCFE나 세후 영업이익 기반 FCFF와 다릅니다.",
            "영업현금흐름 − |자본적지출|",
            period=cash_period,
        ),
        metric(
            "fcf_yield",
            "FCF 수익률",
            ratio(fcf, snapshot.get("market_cap"), 100) if same_currency else None,
            "%",
            "최근 연간 FCF를 현재 시가총액과 비교합니다. 채무 구조와 업종도 함께 봐야 합니다.",
            "연간 단순 FCF ÷ 현재 시가총액 × 100",
            period=f"재무 {cash_period} / 시가총액 조회 시점",
            reason="FCF·시가총액 누락 또는 재무·거래 통화 불일치/미확인입니다.",
        ),
        metric(
            "net_debt",
            "순차입금",
            net_debt,
            financial_unit,
            "총차입금에서 현금성 자산을 뺀 값. 음수이면 순현금 상태입니다.",
            "총차입금 − 현금 및 단기투자",
            period=balance_period,
        ),
        metric(
            "debt_equity",
            "차입금/자기자본",
            ratio(debt, details.get("equity"), 100),
            "%",
            "자기자본 대비 차입 부담. 총부채 비율과 다르며 자본잠식일 때 계산하지 않습니다.",
            "총차입금 ÷ 자기자본 × 100",
            period=balance_period,
        ),
        metric(
            "current_ratio",
            "유동비율",
            ratio(details.get("current_assets"), details.get("current_liabilities"), 100),
            "%",
            "단기 채무를 유동자산으로 충당하는 능력입니다. 재고의 현금화 가능성도 확인해야 합니다.",
            "유동자산 ÷ 유동부채 × 100",
            period=details.get("current_assets_period") or "결산일 미제공",
        ),
    ]
    tech_definitions = [
        (
            "rsi_14",
            "RSI · 14일",
            "",
            "상승과 하락의 강도. 70/30은 관행적 과열/침체 구간이며 자동 매매 신호가 아닙니다.",
            "100 − 100/(1 + Wilder 평균상승/평균하락)",
        ),
        (
            "macd",
            "MACD · 12/26",
            currency,
            "단기와 장기 지수이평 차이로 모멘텀을 확인합니다.",
            "EMA12 − EMA26",
        ),
        (
            "macd_signal",
            "MACD 시그널 · 9",
            currency,
            "MACD의 완만한 추세선입니다. 교차 신호는 횡보장에서 잦은 오류가 생깁니다.",
            "MACD의 EMA9",
        ),
        (
            "macd_histogram",
            "MACD 히스토그램",
            currency,
            "MACD와 시그널의 차이. 추세 가속·둔화를 살핍니다.",
            "MACD − 시그널",
        ),
        (
            "bollinger_upper",
            "볼린저 상단 · 20일",
            currency,
            "최근 변동성에 따른 상단 범위. 상단 돌파가 곧 매도 신호는 아닙니다.",
            "SMA20 + 2 × 종가 표준편차(모집단)",
        ),
        (
            "bollinger_middle",
            "볼린저 중심 · 20일",
            currency,
            "밴드 중심인 최근 20거래일 평균 종가입니다.",
            "SMA20",
        ),
        (
            "bollinger_lower",
            "볼린저 하단 · 20일",
            currency,
            "최근 변동성에 따른 하단 범위. 미래가격 신뢰구간은 아닙니다.",
            "SMA20 − 2 × 종가 표준편차(모집단)",
        ),
        (
            "volume_ratio",
            "거래량 배율",
            "배",
            "최근 거래량이 직전 20거래일 평균의 몇 배인지 보여줍니다.",
            "최근 거래량 ÷ 직전 20일 평균 거래량",
        ),
    ]
    trend = [
        metric(key, label, technical.get(key), unit, description, formula)
        for key, label, unit, description, formula in tech_definitions
    ]
    for days in (20, 60, 100):
        trend.append(
            metric(
                f"ma_{days}",
                f"{days}일 이동평균",
                (snapshot.get("moving_averages") or {}).get(f"ma_{days}"),
                currency,
                "최근 거래일 종가의 평균으로 추세를 살핍니다. 후행 지표입니다.",
                f"최근 {days}개 종가 평균",
            )
        )
    trend.extend(
        [
            metric(
                "atr_20",
                "ATR · 20일",
                snapshot.get("atr_20"),
                currency,
                "갭을 포함한 가격 변동폭의 평균입니다. 방향을 예측하지 않습니다.",
                "최근 20일 True Range 단순평균",
            ),
            metric(
                "volatility",
                "20일 연환산 변동성",
                snapshot.get("volatility_20d_pct"),
                "%",
                "최근 수익률의 흔들림을 연간 척도로 환산합니다.",
                "20일 일수익률 표본표준편차 × √252 × 100",
            ),
            metric(
                "drawdown",
                "1년 최대 낙폭",
                snapshot.get("max_drawdown_1y_pct"),
                "%",
                "조회 구간 내 고점에서 저점까지 가장 큰 하락입니다.",
                "min(종가 ÷ 이전 누적고점 − 1) × 100",
            ),
            metric(
                "beta",
                "베타",
                snapshot.get("beta"),
                "",
                "시장 변화에 대한 상대 민감도. 기준 지수와 추정 기간에 영향을 받습니다.",
                "공급자 제공 시장 대비 수익률 민감도",
                period="공급자 기준 · 추정 기간 미제공",
            ),
        ]
    )
    for name, metrics in (
        ("가치평가", valuation),
        ("수익성·성장", quality),
        ("현금흐름·재무안정성", cash_metrics),
        ("추세·모멘텀·위험", trend),
    ):
        groups.append(dict(name=name, metrics=metrics))
    gaps = []
    if not same_currency:
        gaps.append("재무·거래 통화가 다르거나 확인되지 않아 통화를 섞는 가치 계산을 생략했습니다.")
    missing = sum(m["value"] is None for group in groups for m in group["metrics"])
    if missing:
        gaps.append(f"추가 지표 {missing}개는 데이터 부족 또는 적용 불가로 계산하지 않았습니다.")
    gaps.append(
        "제공 비율의 기준일과 연간 공시 기간은 다를 수 있습니다. 실시간 체결가·증권사 컨센서스는 아닙니다."
    )
    return dict(groups=groups, dataGaps=gaps)


def valuation_inputs(snapshot: dict) -> dict:
    details = snapshot.get("financial_details") or {}
    same_currency = bool(
        snapshot.get("currency") and snapshot.get("currency") == details.get("financialCurrency")
    )
    result = {"price": snapshot.get("price"), "currency": snapshot.get("currency")}
    for target, source in (
        ("eps", "trailingEps"),
        ("book_value_per_share", "bookValue"),
        ("ebitda", "annual_ebitda"),
        ("cash", "cash"),
        ("debt", "debt"),
        ("shares", "sharesOutstanding"),
    ):
        result[target] = finite(details.get(source)) if same_currency else None
    result["notes"] = (
        "Yahoo 제공 EPS(TTM)·BPS·연간 EBITDA·최근 연간 현금/차입금·현재 주식수. "
        "통화 일치 시에만 사용. 증권사 전망치 아님."
    )
    result["periods"] = {key: details.get(f"{key}_period") for key in ("annual_ebitda", "cash", "debt")}
    return result


def indicators_ai_context(panel: dict) -> dict:
    """화면 설명문을 빼고 Gemini가 해석할 값·출처·시점만 반환한다."""
    groups = []
    for group in panel.get("groups", []):
        metrics = [
            {key: metric.get(key) for key in ("key", "label", "value", "unit", "source", "period")}
            for metric in group.get("metrics", [])
            if metric.get("value") is not None
        ]
        if metrics:
            groups.append({"name": group.get("name", ""), "metrics": metrics})
    return {"groups": groups, "dataGaps": list(panel.get("dataGaps", []))}

"""사용자 가정을 명시적으로 받는 상대가치·FCFF 할인 시나리오."""

# ruff: noqa: RUF001 -- 사용자에게 표시하는 수식의 곱셈·뺄셈 기호.

from research.indicators import finite


def calculate_valuation(inputs: dict, assumptions: dict) -> dict:
    if not isinstance(inputs, dict) or not isinstance(assumptions, dict):
        raise ValueError("inputs와 assumptions는 객체여야 합니다.")
    allowed = {
        "target_pe",
        "target_pb",
        "target_ev_ebitda",
        "fcff",
        "growth_pct",
        "discount_pct",
        "terminal_growth_pct",
    }
    if set(assumptions) - allowed:
        raise ValueError("지원하지 않는 가정 항목입니다.")
    values = {}
    for key, value in assumptions.items():
        number = finite(value)
        if number is None or abs(number) > 1e18:
            raise ValueError(f"{key}: 유한한 범위의 숫자가 필요합니다.")
        if key.startswith("target_") and not 0 < number <= 1000:
            raise ValueError(f"{key}: 배수는 0 초과 1000 이하여야 합니다.")
        if key in {"growth_pct", "terminal_growth_pct"} and not -100 < number <= 100:
            raise ValueError(f"{key}: 성장률은 -100% 초과 100% 이하여야 합니다.")
        if key == "discount_pct" and not 0 < number <= 100:
            raise ValueError("WACC는 0% 초과 100% 이하여야 합니다.")
        if key == "fcff" and number <= 0:
            raise ValueError("이 단순 성장 모형은 양수의 정상화된 연간 FCFF가 필요합니다.")
        values[key] = number
    raw = {}
    for key in ("price", "eps", "book_value_per_share", "ebitda", "cash", "debt", "shares"):
        value = inputs.get(key)
        number = finite(value)
        if value is not None and (number is None or abs(number) > 1e18):
            raise ValueError(f"{key}: 유효한 숫자가 필요합니다.")
        raw[key] = number
    if raw["price"] is None or raw["price"] <= 0:
        raise ValueError("양수 기준 가격이 필요합니다.")
    methods = []

    def add(name, value, formula, reason=""):
        if value is not None and (finite(value) is None or value <= 0):
            value, reason = (
                None,
                "계산된 주주가치가 0 이하이거나 범위를 벗어나 주당 가격을 제시하지 않습니다.",
            )
        methods.append(
            dict(
                method=name,
                value=value,
                upside_pct=finite((value / raw["price"] - 1) * 100) if value is not None else None,
                formula=formula,
                reason=reason,
            )
        )

    for key, base, label, formula in (
        ("target_pe", "eps", "PER 시나리오", "제공 EPS(TTM) × 사용자 적용 PER"),
        ("target_pb", "book_value_per_share", "PBR 시나리오", "제공 BPS × 사용자 적용 PBR"),
    ):
        if key in values:
            valid = raw[base] is not None and raw[base] > 0
            add(
                label,
                raw[base] * values[key] if valid else None,
                formula,
                "양수 주당 기초값이 없거나 통화가 확인되지 않았습니다." if not valid else "",
            )
    capital_valid = (
        raw["cash"] is not None
        and raw["cash"] >= 0
        and raw["debt"] is not None
        and raw["debt"] >= 0
        and raw["shares"] is not None
        and raw["shares"] > 0
    )
    if "target_ev_ebitda" in values:
        valid = capital_valid and raw["ebitda"] is not None and raw["ebitda"] > 0
        price = (
            (raw["ebitda"] * values["target_ev_ebitda"] + raw["cash"] - raw["debt"]) / raw["shares"]
            if valid
            else None
        )
        add(
            "EV/EBITDA 시나리오",
            price,
            "(연간 EBITDA × 적용 배수 + 현금 − 차입금) ÷ 현재 주식수",
            "양수 EBITDA·주식수·현금·차입금 또는 일치하는 통화가 필요합니다." if not valid else "",
        )
    dcf_keys = {"fcff", "growth_pct", "discount_pct", "terminal_growth_pct"}
    if dcf_keys & values.keys():
        missing = dcf_keys - values.keys()
        value, reason = None, ""
        if missing:
            reason = "DCF 가정 누락: " + ", ".join(sorted(missing))
        elif values["discount_pct"] <= values["terminal_growth_pct"]:
            raise ValueError("WACC는 영구성장률보다 커야 합니다.")
        elif not capital_valid:
            reason = "현금·차입금·양수 주식수 또는 일치하는 통화가 필요합니다."
        else:
            growth, discount, terminal = (
                values[key] / 100 for key in ("growth_pct", "discount_pct", "terminal_growth_pct")
            )
            if discount <= terminal:
                raise ValueError("할인율과 영구성장률의 차이가 계산 가능한 범위보다 작습니다.")
            flows = [values["fcff"] * (1 + growth) ** year for year in range(1, 6)]
            enterprise = sum(flow / (1 + discount) ** year for year, flow in enumerate(flows, 1))
            enterprise += flows[-1] * (1 + terminal) / (discount - terminal) / (1 + discount) ** 5
            value = (enterprise + raw["cash"] - raw["debt"]) / raw["shares"]
        add(
            "DCF · FCFF 5년 시나리오",
            value,
            "[Σ FCFFₜ/(1+WACC)ᵗ + FCFF₅×(1+g)/(WACC−g)/(1+WACC)⁵ + 현금 − 차입금] ÷ 주식수",
            reason,
        )
    return {
        "methods": methods,
        "dataGaps": [
            "사용자 가정에 따른 단순 시나리오이며 증권사 컨센서스·확정 목표가가 아닙니다.",
            "EV/DCF는 소수주주지분·우선주·비영업자산 등의 조정을 생략합니다. "
            "금융업과 복잡한 자본구조에는 한계가 있습니다.",
            "연간 재무·TTM EPS·현재 주식수의 기준 시점은 다를 수 있습니다. "
            "FCFF는 단순 FCF와 구별해 직접 입력해야 합니다.",
        ],
    }

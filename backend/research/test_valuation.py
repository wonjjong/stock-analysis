import json

import pytest
from django.test import Client, RequestFactory

from research.fundamentals import FundamentalMetrics
from research.indicators import build_indicators, indicators_ai_context, valuation_inputs
from research.lab_preview import build_lab_preview
from research.valuation import calculate_valuation
from research.views import valuation_scenario


@pytest.fixture
def inputs():
    return dict(
        price=100, eps=5, book_value_per_share=40, ebitda=200, cash=50, debt=100, shares=10, currency="USD"
    )


def test_relative_valuation_uses_explicit_multiples(inputs):
    result = calculate_valuation(inputs, dict(target_pe=20, target_pb=3, target_ev_ebitda=6))
    assert [m["value"] for m in result["methods"]] == [100, 120, 115]
    assert result["methods"][1]["upside_pct"] == pytest.approx(20)
    assert calculate_valuation(inputs, {})["methods"] == []


def test_dcf_zero_growth_perpetuity_and_net_debt(inputs):
    result = calculate_valuation(inputs, dict(fcff=100, growth_pct=0, discount_pct=10, terminal_growth_pct=0))
    # 100 / 10% = 1000 enterprise; net debt 50; 10 shares.
    assert result["methods"][0]["value"] == pytest.approx(95)


@pytest.mark.parametrize(
    "assumptions",
    [
        {"target_pe": 0},
        {"target_pb": -1},
        {"target_pe": True},
        {"target_pe": float("nan")},
        {"target_pe": float("inf")},
        {"target_pe": 1e308},
        {"target_pe": 10**400},
        {"surprise": 1},
        {"fcff": -1},
        {"growth_pct": -100},
        {"discount_pct": 0},
        dict(fcff=100, growth_pct=3, discount_pct=2, terminal_growth_pct=2),
    ],
)
def test_invalid_assumptions_are_rejected(inputs, assumptions):
    with pytest.raises(ValueError):
        calculate_valuation(inputs, assumptions)


def test_missing_and_negative_earnings_do_not_create_targets(inputs):
    result = calculate_valuation(
        {**inputs, "eps": -2, "cash": None}, dict(target_pe=20, target_ev_ebitda=6, fcff=100)
    )
    assert all(m["value"] is None and m["reason"] for m in result["methods"])


def test_nonpositive_equity_value_is_not_a_negative_stock_price(inputs):
    result = calculate_valuation({**inputs, "debt": 10000}, {"target_ev_ebitda": 6})
    assert result["methods"][0]["value"] is None


def test_extreme_inputs_never_emit_infinity_or_divide_by_zero(inputs):
    result = calculate_valuation({**inputs, "price": 1e-320}, {"target_pe": 20})
    assert result["methods"][0]["upside_pct"] is None
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="할인율"):
        calculate_valuation(inputs, dict(fcff=1, growth_pct=0, discount_pct=5e-324, terminal_growth_pct=0))


def flatten(panel):
    return {m["key"]: m for g in panel["groups"] for m in g["metrics"]}


def test_financial_ratios_and_filing_priority():
    snapshot = build_lab_preview()["result"]["snapshot"].as_dict()
    filing = FundamentalMetrics("DART", "2025", trailing_pe=12, price_to_book=2)
    metrics = flatten(build_indicators(snapshot, filing))
    assert metrics["trailing_pe"]["value"] == 12
    assert metrics["trailing_pe"]["source"] == "DART"
    assert metrics["fcf"]["value"] == 290_000_000
    assert metrics["fcf_yield"]["value"] == pytest.approx(290 / 12400 * 100)
    assert metrics["roe"]["value"] == 16
    assert metrics["current_ratio"]["value"] == 200
    assert all(m["description"] and m["formula"] and m["period"] for m in metrics.values())


def test_currency_mismatch_and_financial_period_mismatch():
    snapshot = build_lab_preview()["result"]["snapshot"].as_dict()
    snapshot["financial_details"]["financialCurrency"] = "KRW"
    metrics = flatten(build_indicators(snapshot))
    assert metrics["fcf_yield"]["value"] is None
    assert valuation_inputs(snapshot)["eps"] is None
    assert valuation_inputs(snapshot)["shares"] is None
    snapshot["financial_details"]["capex_period"] = "2024-12-31"
    assert flatten(build_indicators(snapshot))["fcf"]["value"] is None


def test_missing_pe_explains_the_data_gap():
    snapshot = build_lab_preview()["result"]["snapshot"].as_dict()
    snapshot["financial_details"]["trailingEps"] = -1
    snapshot["trailing_pe"] = None
    snapshot["financial_details"]["forwardPE"] = None
    metrics = flatten(build_indicators(snapshot))
    assert metrics["trailing_pe"]["value"] is None
    assert "EPS가 0 이하" in metrics["trailing_pe"]["missing_reason"]
    assert "예상 EPS 또는 예상 PER" in metrics["forward_pe"]["missing_reason"]

    snapshot["financial_details"]["trailingEps"] = None
    filing = FundamentalMetrics("DART", "2025", trailing_pe=None, price_to_book=2)
    metrics = flatten(build_indicators(snapshot, filing))
    assert "최근 연간 순이익이 없습니다" in metrics["trailing_pe"]["missing_reason"]


def test_ai_indicator_context_omits_ui_explanations_and_missing_metrics():
    panel = build_indicators(build_lab_preview()["result"]["snapshot"].as_dict())
    compact = indicators_ai_context(panel)
    metrics = [metric for group in compact["groups"] for metric in group["metrics"]]
    assert metrics
    assert all("description" not in metric and "formula" not in metric for metric in metrics)
    assert all(metric["value"] is not None for metric in metrics)


def test_valuation_endpoint_success_and_bad_json(inputs):
    factory = RequestFactory()
    request = factory.post(
        "/api/research/valuation",
        data=json.dumps({"inputs": inputs, "assumptions": {"target_pe": 20}}),
        content_type="application/json",
    )
    response = valuation_scenario(request)
    assert response.status_code == 200
    assert json.loads(response.content)["methods"][0]["value"] == 100
    for data in ("[]", "{", '{"inputs": null, "assumptions": {}}'):
        response = valuation_scenario(
            factory.post("/api/research/valuation", data=data, content_type="application/json")
        )
        assert response.status_code == 400


def test_endpoint_keeps_csrf_and_post_only():
    client = Client(enforce_csrf_checks=True)
    assert (
        client.post("/api/research/valuation", data="{}", content_type="application/json").status_code == 403
    )
    assert client.get("/api/research/valuation").status_code == 405


def test_preview_renders_metric_explanations_and_zero_values():
    response = Client().get("/research/lab/preview")
    assert response.status_code == 200
    html = response.content.decode()
    assert "가정별 가치평가" in html and "MACD" in html and "FCF 수익률" in html
    assert 'id="valuation-input-data"' in html
    assert "용어·계산 기준" in html

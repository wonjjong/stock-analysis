"""
인사이트 조립 동일성.

`rule_insight` 는 LLM 이 없을 때 실제로 저장되는 값이고, `llm_insight` 는 모델이 뭘 주든
저장 형태를 고정하는 검증 계층이다. 둘 다 값이 하나라도 다르면 화면에 다르게 보인다.
"""

from __future__ import annotations

import pytest

from news.crawler.insights import (
    Insight,
    deserves_llm,
    llm_insight,
    rule_insight,
)
from news.crawler.symbols import match_symbols

# TS 의 camelCase 필드 ↔ Python 의 snake_case
_FIELDS = {
    "summary": "summary",
    "keywords": "keywords",
    "sectors": "sectors",
    "evidence": "evidence",
    "sentiment": "sentiment",
    "sentimentScore": "sentiment_score",
    "materiality": "materiality",
    "eventType": "event_type",
    "impactHorizon": "impact_horizon",
    "marketView": "market_view",
    "scoreAdjustment": "score_adjustment",
    "engine": "engine",
    "model": "model",
}


def test_rule_insight_cases_match(parity: dict) -> None:
    cases = parity.get("ruleInsight")
    if not cases:
        pytest.skip("정답지에 ruleInsight 기준값이 없습니다.")

    problems: list[str] = []
    for case in cases:
        actual = rule_insight(case["title"], case["body"])
        expected = case["insight"]
        for js_field, py_field in _FIELDS.items():
            want = expected[js_field]
            got = getattr(actual, py_field)
            if got != want:
                problems.append(
                    f"  {case['title'][:26]}… {js_field}\n    기대 {want!r}\n    실제 {got!r}"
                )
    assert not problems, "ruleInsight 불일치 {}건:\n{}".format(
        len(problems), "\n".join(problems)
    )


def _base() -> Insight:
    return Insight(
        summary="규칙 요약",
        keywords=["규칙키워드"],
        sectors=["반도체"],
        evidence=["규칙 근거"],
        sentiment="중립",
        sentiment_score=50,
        materiality="보통",
        event_type="산업·시장동향",
        impact_horizon="당일",
        market_view="규칙 관점",
        score_adjustment=0,
    )


def test_llm_insight_uses_model_values() -> None:
    parsed = {
        "summary": "  모델 요약  ",
        "keywords": ["가", "나"],
        "sectors": ["2차전지"],
        "evidence": ["모델 근거"],
        "sentiment": "긍정",
        "sentimentScore": 77,
        "materiality": "높음",
        "eventType": "  실적·가이던스  ",
        "impactHorizon": "중기(1~2분기)",
        "marketView": " 모델 관점 ",
        "scoreAdjustment": 5,
    }
    out = llm_insight(parsed, _base(), "Groq", "llama-3.3-70b")
    assert out.summary == "모델 요약"
    assert out.keywords == ["가", "나"]
    assert out.sectors == ["2차전지"]
    assert out.sentiment == "긍정"
    assert out.sentiment_score == 77
    assert out.event_type == "실적·가이던스"
    assert out.market_view == "모델 관점"
    assert out.engine == "Groq"
    assert out.model == "llama-3.3-70b"


def test_llm_insight_falls_back_on_garbage() -> None:
    """모델이 엉뚱한 값을 주면 규칙 기반 값으로 떨어진다 — 저장 형태가 깨지지 않는다."""
    parsed = {
        "summary": 12345,
        "keywords": "배열이 아님",
        "sectors": [],
        "evidence": [None, 42],
        "sentiment": "매우긍정",
        "sentimentScore": "숫자아님",
        "materiality": "아주높음",
        "eventType": "   ",
        "impactHorizon": "영원히",
        "marketView": None,
        "scoreAdjustment": float("nan"),
    }
    base = _base()
    out = llm_insight(parsed, base, "환경변수", "gpt")
    assert out.summary == base.summary
    assert out.keywords == base.keywords
    assert out.sectors == base.sectors, "빈 sectors 는 규칙 값으로 대체된다"
    assert out.evidence == base.evidence
    assert out.sentiment == base.sentiment
    assert out.sentiment_score == base.sentiment_score
    assert out.materiality == base.materiality
    assert out.event_type == base.event_type
    assert out.impact_horizon == base.impact_horizon
    assert out.market_view == base.market_view
    assert out.score_adjustment == base.score_adjustment


def test_llm_insight_clamps_ranges() -> None:
    base = _base()
    assert llm_insight({"sentimentScore": 999}, base, "x", "y").sentiment_score == 100
    assert llm_insight({"sentimentScore": -5}, base, "x", "y").sentiment_score == 0
    assert llm_insight({"scoreAdjustment": 99}, base, "x", "y").score_adjustment == 8
    assert llm_insight({"scoreAdjustment": -99}, base, "x", "y").score_adjustment == -8


def test_llm_insight_rounds_like_javascript() -> None:
    """JS `Math.round` 는 .5 를 +∞ 로 올린다. Python `round()` 는 짝수로 붙인다."""
    base = _base()
    assert llm_insight({"sentimentScore": 2.5}, base, "x", "y").sentiment_score == 3
    assert llm_insight({"scoreAdjustment": -0.5}, base, "x", "y").score_adjustment == 0


def test_deserves_llm() -> None:
    base = _base()
    symbols = match_symbols("", "삼성전자 관련 기사")
    assert deserves_llm(base, symbols, 0) is True, "종목이 잡히면 보낸다"

    low = Insight(summary="", materiality="낮음")
    assert deserves_llm(low, [], 0) is False, "종목 없고 중요도 낮고 본문 짧으면 안 보낸다"
    assert deserves_llm(low, [], 1_200) is True, "본문이 길면 보낸다"
    assert deserves_llm(base, [], 0) is True, "중요도가 낮음이 아니면 보낸다"

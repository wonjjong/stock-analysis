"""
인사이트 조립. `app/lib/news-insights.ts` 의 순수 부분 이식
(ruleInsight / llmInsight / deservesLlm / 검증 헬퍼).

DB 와 네트워크를 만지는 큐 처리는 `news/services/insights.py` 에 있다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .analysis import analyze_news_locally
from .keywords import extract_keywords
from .symbols import SymbolMatch, match_symbols

LLM_BODY_LIMIT = 6_000
RULE_TEXT_LIMIT = 8_000

HORIZONS = ("당일", "단기(1~4주)", "중기(1~2분기)", "장기(1년+)")
SENTIMENTS = ("긍정", "부정", "중립")
MATERIALITIES = ("높음", "보통", "낮음")

_LINE_SPLIT = re.compile(r"\n+")

SYSTEM_PROMPT = " ".join([
    "당신은 기관투자자를 위한 뉴스 애널리스트다.",
    "기사에 명시된 사실만 사용하고 없는 수치를 만들어내지 않는다.",
    "한국어로 답하고 반드시 지정한 JSON 객체 하나만 출력한다.",
    "필드: summary(3문장 이내 요약), keywords(핵심 키워드 3~8개), sectors(영향 업종 0~4개),",
    "evidence(기사에서 인용한 근거 문장 1~3개), sentiment(긍정|부정|중립), sentimentScore(0~100),",
    "materiality(높음|보통|낮음), eventType(짧은 사건 유형),"
    " impactHorizon(당일|단기(1~4주)|중기(1~2분기)|장기(1년+)),",
    "marketView(시황·업종 관점 한두 문장), scoreAdjustment(-8~8 정수),"
    " symbols(기사가 직접 다루는 상장사명 0~5개).",
])


@dataclass(slots=True)
class Insight:
    summary: str
    keywords: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    sentiment: str = "중립"
    sentiment_score: int = 50
    materiality: str = "낮음"
    event_type: str = "산업·시장동향"
    impact_horizon: str = "당일"
    market_view: str = ""
    score_adjustment: int = 0
    engine: str = "규칙 기반"
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: Any, low: int, high: int, fallback: int) -> int:
    """
    JS `Number(value)` + `Number.isFinite` + `Math.round` 의미.

    `Math.round` 는 .5 를 +∞ 쪽으로 올리므로 Python `round()`(짝수 붙임)를 쓸 수 없다.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):  # NaN·Inf
        return fallback
    import math

    return max(low, min(high, math.floor(number + 0.5)))


def _string_list(value: Any, limit: int, max_length: int = 60) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()[:max_length]
        if trimmed:
            out.append(trimmed)
        if len(out) >= limit:
            break
    return out


def _pick(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def rule_insight(title: str, body: str) -> Insight:
    """규칙 기반 인사이트. LLM 이 없어도 파이프라인이 도는 근거다."""
    text = f"{title}. {body}"[:RULE_TEXT_LIMIT]
    base = analyze_news_locally(text, "MARKET", "시장 전체")
    symbols = match_symbols(title, body)
    # dict.fromkeys 로 순서를 유지한 중복 제거(JS Set 과 같다).
    sectors = list(dict.fromkeys(item.sector for item in symbols))[:4]
    lead = [line.strip() for line in _LINE_SPLIT.split(body) if len(line.strip()) > 30][:2]

    return Insight(
        summary=(" ".join(lead) or body or title)[:400],
        keywords=extract_keywords(title, body),
        sectors=sectors,
        evidence=base["keyEvidence"],
        sentiment=base["sentiment"],
        sentiment_score=round(base["sentimentScore"]),
        materiality=base["materiality"],
        event_type=base["eventType"],
        impact_horizon=base["impactHorizon"],
        market_view=(
            f"{', '.join(sectors)} 업종에 관련된 보도입니다."
            if sectors
            else "특정 업종을 지목하기 어려운 일반 보도입니다."
        ),
        score_adjustment=base["scoreAdjustment"],
        engine="규칙 기반",
        model="",
    )


def llm_insight(parsed: dict[str, Any], base: Insight, engine: str, model: str) -> Insight:
    """
    모델 응답을 검증해 인사이트로 만든다. 필드가 빠지거나 범위를 벗어나면 규칙 기반
    값으로 떨어진다 — 모델이 뭘 주든 저장되는 값의 형태는 항상 같다.
    """
    keywords = _string_list(parsed.get("keywords"), 8, 30)
    evidence = _string_list(parsed.get("evidence"), 3, 200)
    summary = parsed.get("summary")
    market_view = parsed.get("marketView")
    event_type = parsed.get("eventType")

    sectors = _string_list(parsed.get("sectors"), 4, 30) or base.sectors

    return Insight(
        summary=(summary if isinstance(summary, str) else base.summary).strip()[:800],
        keywords=keywords or base.keywords,
        sectors=sectors,
        evidence=evidence or base.evidence,
        sentiment=_pick(parsed.get("sentiment"), SENTIMENTS, base.sentiment),
        sentiment_score=_clamp(parsed.get("sentimentScore"), 0, 100, base.sentiment_score),
        materiality=_pick(parsed.get("materiality"), MATERIALITIES, base.materiality),
        event_type=(
            event_type.strip()[:40]
            if isinstance(event_type, str) and event_type.strip()
            else base.event_type
        ),
        impact_horizon=_pick(parsed.get("impactHorizon"), HORIZONS, base.impact_horizon),
        market_view=(
            market_view if isinstance(market_view, str) else base.market_view
        ).strip()[:400],
        score_adjustment=_clamp(parsed.get("scoreAdjustment"), -8, 8, base.score_adjustment),
        engine=engine,
        model=model,
    )


def deserves_llm(base: Insight, symbols: list[SymbolMatch], body_chars: int) -> bool:
    """
    규칙 단계에서 종목이 잡혔거나 중요한 기사만 LLM 으로 보낸다. 무료 한도를 아끼기 위한
    선별이다.
    """
    if symbols:
        return True
    if base.materiality != "낮음":
        return True
    return body_chars >= 1_200

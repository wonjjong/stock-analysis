"""규칙 기반 뉴스 감성·중요도·사건 유형 분석."""

from __future__ import annotations

import math
import re
from typing import Any

POSITIVE = ["증가", "성장", "확대", "상향", "수주", "흑자", "개선", "회복", "호조", "승인",
            "돌파", "협력", "투자", "growth", "raise", "raised", "beat", "beats", "surge",
            "record", "improve", "approval", "contract"]
NEGATIVE = ["감소", "하락", "축소", "하향", "적자", "부진", "지연", "규제", "소송", "리콜",
            "중단", "해킹", "우려", "decline", "cut", "miss", "delay", "lawsuit", "recall",
            "probe", "warning", "risk", "sliding"]
MATERIAL = ["실적", "매출", "영업이익", "순이익", "가이던스", "수주", "계약", "인수", "합병",
            "유상증자", "배당", "자사주", "규제", "소송", "earnings", "revenue", "profit",
            "guidance", "forecast", "acquisition", "merger", "dividend", "buyback"]

_WHITESPACE = re.compile(r"\s+")
# 고정폭 lookbehind 두 개. 원본의 가변폭 교대와 같은 지점에서 나뉜다.
_SENTENCE = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s+")

_EARNINGS = re.compile(r"earnings|revenue|guidance|forecast")
_CONTRACT = re.compile(r"contract|order")
_LEGAL = re.compile(r"regulation|lawsuit|probe")
_INVEST = re.compile(r"investment|partnership")

WATCH_ITEMS = [
    "회사 공시 또는 공식 발표로 사실 확인",
    "다음 실적 추정치 변화",
    "동일 사건의 후속 보도와 가격·거래량 반응",
]


def _count(text: str, words: list[str]) -> int:
    normalized = text.lower()
    return sum(1 for word in words if word.lower() in normalized)


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _js_round(value: float) -> int:
    """JS `Math.round`: .5 를 +∞ 쪽으로 올린다."""
    return math.floor(value + 0.5)


def analyze_news_locally(text: str, symbol: str, company: str) -> dict[str, Any]:
    compact = _WHITESPACE.sub(" ", text).strip()
    pos = _count(compact, POSITIVE)
    neg = _count(compact, NEGATIVE)
    important = _count(compact, MATERIAL)
    raw = pos - neg

    sentiment_score = _clamp(50 + raw * 11)
    sentiment = "긍정" if raw > 0 else "부정" if raw < 0 else "중립"
    explicit = symbol.lower() in compact.lower() or company in compact
    relevance = _clamp((76 if explicit else 48) + min(important * 5, 19))
    materiality = "높음" if important >= 3 else "보통" if important >= 1 else "낮음"
    lower = compact.lower()

    if "실적" in compact or "매출" in compact or _EARNINGS.search(lower):
        event_type = "실적·가이던스"
    elif "수주" in compact or "계약" in compact or _CONTRACT.search(lower):
        event_type = "수주·사업계약"
    elif "규제" in compact or "소송" in compact or _LEGAL.search(lower):
        event_type = "규제·법률"
    elif "투자" in compact or "협력" in compact or _INVEST.search(lower):
        event_type = "투자·파트너십"
    else:
        event_type = "산업·시장동향"

    if event_type == "실적·가이던스":
        impact_horizon = "중기(1~2분기)"
    elif event_type == "수주·사업계약":
        impact_horizon = "장기(1년+)"
    elif materiality == "낮음":
        impact_horizon = "당일"
    else:
        impact_horizon = "단기(1~4주)"

    factor = 2.4 if materiality == "높음" else 1.5 if materiality == "보통" else 0.7
    score_adjustment = _js_round(_clamp(raw * factor, -8, 8))

    sentences = [item for item in _SENTENCE.split(compact) if len(item) > 18]
    key_evidence = [item[:150] for item in (sentences or [compact])[:3]]

    direction = (
        "이익 기대 또는 사업 가시성에 우호적" if sentiment == "긍정"
        else "실적 또는 밸류에이션의 하방 위험을 높일 수 있는" if sentiment == "부정"
        else "방향성이 확정되지 않은"
    )

    return {
        "symbol": symbol,
        "sentiment": sentiment,
        "sentimentScore": sentiment_score,
        "relevance": relevance,
        "materiality": materiality,
        "eventType": event_type,
        "impactHorizon": impact_horizon,
        "confidence": _clamp(52 + (15 if explicit else 0) + min(len(compact) / 45, 18) + important * 2),
        "scoreAdjustment": score_adjustment,
        "summary": (
            f"{company} 관련 {event_type} 뉴스입니다. {direction} 신호로 분류했습니다."
        ),
        "keyEvidence": key_evidence,
        "bullCase": (
            "보도 내용이 실제 매출·이익 추정치 상향으로 연결되면 주가 재평가의 근거가 됩니다."
            if pos > 0
            else "추가 공시에서 정량적 성과가 확인되면 중립 판단이 개선될 수 있습니다."
        ),
        "bearCase": (
            "부정 요인이 장기화되거나 비용으로 현실화되면 현재 기대치를 낮춰야 합니다."
            if neg > 0
            else "기사에 계약 금액·이익 기여 시점이 없으면 기대감만 선반영됐을 가능성이 있습니다."
        ),
        "watchItems": list(WATCH_ITEMS),
        "engine": "규칙 기반 데모",
    }

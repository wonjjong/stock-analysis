import json
from typing import TYPE_CHECKING
from app.schemas import NewsAnalysisReport, NewsAnalysisRequest

if TYPE_CHECKING:
    from app.config import Settings


POSITIVE = ("증가", "성장", "확대", "상향", "수주", "흑자", "개선", "회복", "호조", "승인", "협력", "투자")
NEGATIVE = ("감소", "하락", "축소", "하향", "적자", "부진", "지연", "규제", "소송", "리콜", "중단", "우려")
MATERIAL = ("실적", "매출", "영업이익", "순이익", "가이던스", "수주", "계약", "인수", "합병", "배당", "자사주", "규제", "소송")


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def deterministic_news_analysis(request: NewsAnalysisRequest) -> NewsAnalysisReport:
    text = " ".join(request.text.split())
    positive = sum(word in text for word in POSITIVE); negative = sum(word in text for word in NEGATIVE)
    important = sum(word in text for word in MATERIAL); raw = positive - negative
    sentiment = "긍정" if raw > 0 else "부정" if raw < 0 else "중립"
    explicit = request.company in text or request.symbol.lower() in text.lower()
    materiality = "높음" if important >= 3 else "보통" if important >= 1 else "낮음"
    event_type = "실적·가이던스" if any(word in text for word in ("실적", "매출", "영업이익")) else "수주·사업계약" if any(word in text for word in ("수주", "계약")) else "규제·법률" if any(word in text for word in ("규제", "소송")) else "산업·시장동향"
    multiplier = 2.4 if materiality == "높음" else 1.5 if materiality == "보통" else .7
    adjustment = round(_clamp(raw * multiplier, -8, 8))
    evidence = [part.strip()[:180] for part in text.replace("다. ", "다.| ").split("|") if len(part.strip()) > 18][:3] or [text[:180]]
    return NewsAnalysisReport(symbol=request.symbol, sentiment=sentiment, sentiment_score=_clamp(50 + raw * 11), relevance=_clamp((76 if explicit else 48) + min(important * 5, 19)), materiality=materiality, event_type=event_type, impact_horizon="중기(1~2분기)" if event_type == "실적·가이던스" else "장기(1년+)" if event_type == "수주·사업계약" else "단기(1~4주)", confidence=_clamp(52 + (15 if explicit else 0) + min(len(text) / 45, 18) + important * 2), score_adjustment=adjustment, summary=f"{request.company} 관련 {event_type} 뉴스로, {sentiment} 신호로 분류했습니다.", key_evidence=evidence, bull_case="정량적 성과가 실제 실적 추정치에 반영되면 재평가 근거가 됩니다.", bear_case="금액과 이익 기여 시점이 불명확하면 기대감만 선반영됐을 수 있습니다.", watch_items=["회사 공시로 사실 확인", "실적 추정치 변화", "후속 보도와 거래량 반응"], engine="deterministic-fallback")


async def analyze_news(settings: "Settings", request: NewsAnalysisRequest) -> NewsAnalysisReport:
    if not settings.openai_api_key: return deterministic_news_analysis(request)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.parse(model=settings.openai_news_model, store=False, input=[
        {"role":"system","content":"당신은 기관투자자 수준의 뉴스 애널리스트다. 기사에 명시된 사실만 사용하고 사실과 해석을 분리한다. 관련성, 실적 중요도, 영향 기간을 평가하며 추천점수 조정은 -8~+8로 제한한다. 과장된 투자 표현을 쓰지 않는다. engine은 openai로 쓴다."},
        {"role":"user","content":json.dumps(request.model_dump(), ensure_ascii=False)},
    ], text_format=NewsAnalysisReport)
    return response.output_parsed

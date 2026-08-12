import json
from datetime import datetime, timezone
from openai import AsyncOpenAI
from app.config import Settings
from app.schemas import AnalysisReport, Evidence, Recommendation


SYSTEM_PROMPT = """당신은 기관투자자 수준의 시니어 주식 애널리스트다. 제공된 시점 보존 데이터만 사용한다.
수치나 사건을 추측하지 말고, 모든 핵심 주장에 evidence_id를 연결한다. 목표가·매수구간·손절가는 정량엔진 값을 변경하지 않는다.
상승 논리와 반대 논리를 동등하게 검토하고 무효화 조건을 구체적으로 쓴다. 투자 확정 표현을 사용하지 않는다."""


async def create_report(settings: Settings, recommendation: Recommendation, evidence: list[Evidence]) -> AnalysisReport:
    if not settings.openai_api_key:
        return AnalysisReport(symbol=recommendation.symbol, stance=recommendation.action, confidence=round(recommendation.confidence), executive_summary="정량 팩터와 현재 거시환경을 함께 고려할 때 분할 접근이 유효합니다. 데이터 공급자 연결 전에는 데모 보고서로 표시됩니다.", bull_case=["이익 추정치와 가격 추세가 같은 방향", "변동성 조정 기대수익이 기준 통과"], bear_case=["거시 위험선호가 빠르게 악화될 수 있음"], invalidation_conditions=[f"종가가 {recommendation.stop:,.2f} 아래에서 마감", "이익 추정치 2회 연속 하향"], entry_low=recommendation.entry_low, entry_high=recommendation.entry_high, target_price=recommendation.target, stop_price=recommendation.stop, evidence_ids=[str(i) for i in range(len(evidence))], model="deterministic-fallback")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    payload = {"recommendation": recommendation.model_dump(mode="json"), "evidence": [item.model_dump(mode="json") for item in evidence]}
    response = await client.responses.parse(model=settings.openai_report_model, input=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps(payload, ensure_ascii=False)}], text_format=AnalysisReport, store=False)
    report = response.output_parsed
    report.generated_at = datetime.now(timezone.utc); report.model = settings.openai_report_model
    return report

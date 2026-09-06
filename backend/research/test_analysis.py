from research.analysis import Evidence, build_live_report, build_report


def _recommendation() -> dict:
    return {
        "symbol": "005930",
        "score": 81.4,
        "confidence": 78.6,
        "action": "매수 유효",
        "entry_low": 78000,
        "entry_high": 79500,
        "target": 92000,
        "stop": 74800,
        "reasons": ["quality", "momentum"],
    }


def test_llm_can_write_narrative_but_cannot_change_quantitative_plan():
    evidence = [Evidence("news:1", "news", "실적 개선", "공시", "now", "now")]
    parsed = {
        "executiveSummary": "실적과 추세가 함께 개선되고 있습니다.",
        "bullCase": ["이익 추정치 상향"],
        "bearCase": ["수요 둔화"],
        "catalysts": ["신제품 출시"],
        "invalidationConditions": ["추정치 하향"],
        "evidenceIds": ["news:1", "news:999"],
        "targetPrice": 999999,
        "stopPrice": 1,
        "stance": "무조건 매수",
        "confidence": 100,
    }

    report = build_report(parsed, _recommendation(), evidence, "test-model")

    assert report.target_price == 92000
    assert report.stop_price == 74800
    assert report.stance == "매수 유효"
    assert report.confidence == 79
    assert report.evidence_ids == ["news:1"]
    assert report.engine == "test-model"


def test_malformed_llm_output_falls_back_to_quantitative_report():
    report = build_report("not-json", _recommendation(), [], "ignored")

    assert report.engine == "정량 폴백"
    assert report.entry_low == 78000
    assert report.invalidation_conditions == ["종가가 정량 손절가 74,800.00 아래에서 마감"]


def test_live_report_allows_only_known_stance_and_evidence_ids():
    evidence = [Evidence("market:1", "market", "가격", "공급자", "now", "now")]
    parsed = {
        "stance": "무조건 매수",
        "executiveSummary": "공개 데이터에 따른 조건부 분석입니다.",
        "bullCase": ["매출 성장"],
        "bearCase": ["높은 변동성"],
        "catalysts": [],
        "invalidationConditions": ["성장 둔화"],
        "dataGaps": ["최신 공시 미포함"],
        "evidenceIds": ["market:1", "invented:1"],
        "targetPrice": 1000,
    }

    report = build_live_report(parsed, "IREN", evidence, "Google Gemini")

    assert report.symbol == "IREN"
    assert report.stance == "중립"
    assert report.evidence_ids == ["market:1"]
    assert report.engine == "Google Gemini"
    assert not hasattr(report, "target_price")

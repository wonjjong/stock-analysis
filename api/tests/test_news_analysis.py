from app.schemas import NewsAnalysisRequest
from app.services.news_analysis import deterministic_news_analysis


def test_positive_material_news_is_capped():
    request = NewsAnalysisRequest(symbol="005930", company="삼성전자", text="삼성전자 실적과 매출, 영업이익이 증가했다. 대규모 공급 계약과 신규 수주 확대가 확인됐으며 가이던스도 상향됐다.")
    report = deterministic_news_analysis(request)
    assert report.sentiment == "긍정"
    assert report.materiality == "높음"
    assert 0 < report.score_adjustment <= 8
    assert report.relevance >= 75


def test_negative_news_does_not_exceed_floor():
    request = NewsAnalysisRequest(symbol="NVDA", company="NVIDIA", text="NVIDIA 관련 규제와 소송 우려로 제품 승인이 지연됐다. 매출 전망 하향과 공급 축소 가능성도 제기됐다.")
    report = deterministic_news_analysis(request)
    assert report.sentiment == "부정"
    assert -8 <= report.score_adjustment < 0

from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from app.config import get_settings
from app.domain.recommendation import rank_candidates
from app.providers.mock import MOCK_CANDIDATES, MOCK_REGIME
from app.schemas import AnalysisRequest, Evidence, NewsAnalysisReport, NewsAnalysisRequest, Recommendation
from app.services.news_analysis import analyze_news
from app.services.openai_analysis import create_report

app = FastAPI(title="Signalist API", version="0.1.0")


@app.get("/health")
async def health(): return {"status": "ok", "time": datetime.now(timezone.utc)}


@app.get("/v1/recommendations", response_model=list[Recommendation])
async def recommendations(): return rank_candidates(MOCK_CANDIDATES, MOCK_REGIME)


@app.get("/v1/stocks/{symbol}")
async def stock_detail(symbol: str):
    candidate = next((item for item in MOCK_CANDIDATES if item.symbol == symbol.upper()), None)
    if not candidate: raise HTTPException(404, "종목을 찾을 수 없습니다")
    return {"symbol": candidate.symbol, "price": candidate.price, "atr20": candidate.atr_20, "as_of": datetime.now(timezone.utc)}


@app.post("/v1/stocks/{symbol}/analyses")
async def analyze(symbol: str, request: AnalysisRequest):
    row = next((item for item in rank_candidates(MOCK_CANDIDATES, MOCK_REGIME, 20) if item["symbol"] == symbol.upper()), None)
    if not row: raise HTTPException(404, "분석 가능한 종목이 아닙니다")
    rec = Recommendation(**row)
    evidence = [Evidence(kind="market", title="정량 추천 스냅샷", source="Signalist factor engine", observed_at=rec.as_of, available_at=rec.as_of)]
    report = await create_report(get_settings(), rec, evidence)
    return {"refresh": request.refresh, "status": "completed", "report": report}


@app.post("/v1/news/analyses", response_model=NewsAnalysisReport)
async def news_analysis(request: NewsAnalysisRequest):
    return await analyze_news(get_settings(), request)

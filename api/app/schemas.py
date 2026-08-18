from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    kind: str
    title: str
    source: str
    observed_at: datetime
    available_at: datetime
    url: str | None = None


class FactorScore(BaseModel):
    quality: float = Field(ge=0, le=100)
    value: float = Field(ge=0, le=100)
    momentum: float = Field(ge=0, le=100)
    revisions: float = Field(ge=0, le=100)
    news: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)


class Recommendation(BaseModel):
    symbol: str
    score: float
    action: str
    confidence: float
    entry_low: float
    entry_high: float
    target: float
    stop: float
    reasons: list[str]
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisReport(BaseModel):
    symbol: str
    stance: str
    confidence: int = Field(ge=0, le=100)
    executive_summary: str
    bull_case: list[str]
    bear_case: list[str]
    invalidation_conditions: list[str]
    entry_low: float
    entry_high: float
    target_price: float
    stop_price: float
    evidence_ids: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str


class AnalysisRequest(BaseModel):
    refresh: bool = False


class NewsAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    company: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=40, max_length=30000)
    source_url: str | None = None


class NewsAnalysisReport(BaseModel):
    symbol: str
    sentiment: str
    sentiment_score: float = Field(ge=0, le=100)
    relevance: float = Field(ge=0, le=100)
    materiality: str
    event_type: str
    impact_horizon: str
    confidence: float = Field(ge=0, le=100)
    score_adjustment: float = Field(ge=-8, le=8)
    summary: str
    key_evidence: list[str] = Field(min_length=1, max_length=3)
    bull_case: str
    bear_case: str
    watch_items: list[str] = Field(min_length=2, max_length=4)
    engine: str

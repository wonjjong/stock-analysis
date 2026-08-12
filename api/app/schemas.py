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

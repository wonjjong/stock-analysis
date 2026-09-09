"""임의 주식 티커의 공개 시장 데이터 스냅샷을 만든다."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from research.analysis import Evidence
from research.symbols import route_symbol, yfinance_candidates
from research.technical_indicators import technical_metrics


class MarketDataError(RuntimeError):
    """티커 데이터가 없거나 외부 데이터 공급자가 응답하지 않을 때 발생한다."""


@dataclass(frozen=True, slots=True)
class MovingAverages:
    """종가 일봉에서 만든 단기·중기·장기 추세 기준선."""

    ma_20: float | None
    ma_60: float | None
    ma_100: float | None
    price_above_ma_20: bool | None
    price_above_ma_60: bool | None
    price_above_ma_100: bool | None
    alignment: str


@dataclass(frozen=True, slots=True)
class PriceChartPoint:
    """차트에만 쓰는 일별 종가와 이동평균 값.

    AI 입력에는 넣지 않는다. 장기 가격 이력은 화면에서 검증할 수 있게 별도로 보관한다.
    """

    date: str
    open: float
    high: float
    low: float
    close: float
    ma_20: float | None
    ma_60: float | None
    ma_100: float | None


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    company: str
    exchange: str
    currency: str
    sector: str
    observed_at: str
    price: float
    market_cap: float | None
    return_1d_pct: float | None
    return_1m_pct: float | None
    return_6m_pct: float | None
    return_1y_pct: float | None
    high_52w: float | None
    distance_from_high_pct: float | None
    volatility_20d_pct: float | None
    atr_20: float | None
    moving_averages: MovingAverages
    chart_points: tuple[PriceChartPoint, ...]
    max_drawdown_1y_pct: float | None
    avg_volume_20d: float | None
    beta: float | None
    trailing_pe: float | None
    price_to_book: float | None
    revenue_growth_pct: float | None
    gross_margin_pct: float | None
    profit_margin_pct: float | None
    financial_period: str
    total_revenue: float | None
    net_income: float | None
    ebitda: float | None
    cash_and_short_term_investments: float | None
    total_debt: float | None
    operating_cash_flow: float | None
    capital_expenditure: float | None
    technical: dict[str, float | None] = field(default_factory=dict)
    financial_details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # AI에는 요약 지표만 전달한다. 일별 가격 이력은 화면 차트 전용 데이터다.
        del result["chart_points"]
        return result


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pct(value: object) -> float | None:
    number = _finite(value)
    return number * 100 if number is not None else None


def _window_return(closes: Any) -> float | None:
    """조회 구간 전체의 수익률.

    거래일 수로 1년을 세면 시장마다 답이 달라진다(미국 약 252일, 한국 약 245일). period="1y"
    로 받은 구간의 처음과 끝을 그대로 쓰면 시장에 상관없이 맞는다. 예전에는 251 세션을
    요구해 한국 종목의 1년 수익률이 조용히 비었다.
    """
    if len(closes) < 2:
        return None
    start = _finite(closes.iloc[0])
    end = _finite(closes.iloc[-1])
    if start in (None, 0) or end is None:
        return None
    return (end / start - 1) * 100


def _period_return(closes: Any, sessions: int) -> float | None:
    if len(closes) <= sessions:
        return None
    start = _finite(closes.iloc[-sessions - 1])
    end = _finite(closes.iloc[-1])
    if start in (None, 0) or end is None:
        return None
    return (end / start - 1) * 100


def moving_averages(closes: Any, price: float) -> MovingAverages:
    """최근 종가만으로 20·60·100일 이평과 배열 상태를 만든다."""
    values = [number for value in closes if (number := _finite(value)) is not None]

    def average(days: int) -> float | None:
        if len(values) < days:
            return None
        return sum(values[-days:]) / days

    ma_20, ma_60, ma_100 = average(20), average(60), average(100)
    if ma_20 is None or ma_60 is None or ma_100 is None:
        alignment = "이평 데이터 부족"
    elif ma_20 > ma_60 > ma_100:
        alignment = "정배열"
    elif ma_20 < ma_60 < ma_100:
        alignment = "역배열"
    else:
        alignment = "혼조"

    return MovingAverages(
        ma_20=ma_20,
        ma_60=ma_60,
        ma_100=ma_100,
        price_above_ma_20=price > ma_20 if ma_20 is not None else None,
        price_above_ma_60=price > ma_60 if ma_60 is not None else None,
        price_above_ma_100=price > ma_100 if ma_100 is not None else None,
        alignment=alignment,
    )


def price_chart_points(
    rows: list[tuple[str, float, float, float, float]], limit: int = 120
) -> tuple[PriceChartPoint, ...]:
    """최근 일봉과 각 시점의 이평을 차트에 필요한 최소 형태로 자른다."""
    daily = [row for row in rows if all(math.isfinite(value) for value in row[1:])]

    def average(index: int, days: int) -> float | None:
        if index + 1 < days:
            return None
        return sum(close for *_, close in daily[index - days + 1 : index + 1]) / days

    start = max(0, len(daily) - limit)
    return tuple(
        PriceChartPoint(
            date=date,
            open=open_price,
            high=high,
            low=low,
            close=close,
            ma_20=average(index, 20),
            ma_60=average(index, 60),
            ma_100=average(index, 100),
        )
        for index, (date, open_price, high, low, close) in enumerate(daily[start:], start=start)
    )


def _latest_statement_value(frame: Any, labels: tuple[str, ...]) -> tuple[float | None, str]:
    if frame is None or frame.empty:
        return None, ""
    for column in frame.columns:
        for label in labels:
            if label in frame.index:
                value = _finite(frame.at[label, column])
                if value is not None:
                    period = column.date().isoformat() if hasattr(column, "date") else str(column)
                    return value, period
    return None, ""


def _statement_values(ticker: Any) -> tuple[dict[str, float | None], str]:
    frames = {}
    for name, attribute in (
        ("income", "income_stmt"),
        ("balance", "balance_sheet"),
        ("cashflow", "cashflow"),
    ):
        try:
            frames[name] = getattr(ticker, attribute)
        except Exception:
            frames[name] = None
    definitions = {
        "total_revenue": ("income", ("Total Revenue", "Operating Revenue")),
        "net_income": ("income", ("Net Income", "Net Income Common Stockholders")),
        "ebitda": ("income", ("EBITDA", "Normalized EBITDA")),
        "cash_and_short_term_investments": (
            "balance",
            ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
        ),
        "total_debt": ("balance", ("Total Debt",)),
        "operating_cash_flow": (
            "cashflow",
            ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
        ),
        "capital_expenditure": ("cashflow", ("Capital Expenditure",)),
    }
    result: dict[str, float | None] = {}
    periods: list[str] = []
    for name, (frame_name, labels) in definitions.items():
        result[name], period = _latest_statement_value(frames[frame_name], labels)
        if period:
            periods.append(period)
    return result, max(periods, default="")


def _financial_details(ticker: Any, info: dict) -> dict[str, Any]:
    """추가 지표의 연간 재무값은 동일 결산 열에서 읽고 누락은 그대로 둔다."""
    result = {
        key: _finite(info.get(key))
        for key in (
            "trailingEps",
            "forwardEps",
            "forwardPE",
            "bookValue",
            "sharesOutstanding",
            "enterpriseToEbitda",
            "returnOnEquity",
            "returnOnAssets",
            "operatingMargins",
        )
    }
    result["financialCurrency"] = str(info.get("financialCurrency") or "")
    definitions = {
        "income_stmt": {"annual_ebitda": ("EBITDA",), "annual_income": ("Net Income",)},
        "balance_sheet": {
            "cash": ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
            "debt": ("Total Debt",),
            "equity": ("Stockholders Equity",),
            "current_assets": ("Current Assets",),
            "current_liabilities": ("Current Liabilities",),
        },
        "cashflow": {
            "ocf": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
            "capex": ("Capital Expenditure",),
        },
    }
    for attribute, fields in definitions.items():
        try:
            frame = getattr(ticker, attribute)
            if frame is None or frame.empty:
                continue
            column = max(frame.columns)
            period = column.date().isoformat() if hasattr(column, "date") else str(column)
            for key, labels in fields.items():
                result[key] = next(
                    (
                        value
                        for label in labels
                        if label in frame.index
                        if (value := _finite(frame.at[label, column])) is not None
                    ),
                    None,
                )
                result[f"{key}_period"] = period
        except Exception:
            # 보조 지표 누락이 종목 분석 전체를 중단시키지 않는다.
            continue
    return result


def _news_evidence(ticker: Any, available_at: str, limit: int = 8) -> list[Evidence]:
    result: list[Evidence] = []
    for row in ticker.news[:limit]:
        content = row.get("content") if isinstance(row, dict) else None
        if not isinstance(content, dict):
            content = row if isinstance(row, dict) else {}
        title = str(content.get("title") or "").strip()
        if not title:
            continue
        provider = content.get("provider")
        source = provider.get("displayName") if isinstance(provider, dict) else "Yahoo Finance"
        canonical = content.get("canonicalUrl")
        url = canonical.get("url") if isinstance(canonical, dict) else content.get("link") or ""
        raw_date = content.get("pubDate") or content.get("providerPublishTime")
        try:
            observed_at = (
                datetime.fromtimestamp(raw_date, UTC).isoformat()
                if isinstance(raw_date, (int, float))
                else str(raw_date or "")
            )
        except (ValueError, OverflowError, OSError):
            observed_at = ""
        result.append(
            Evidence(
                id=f"external-news:{content.get('id') or row.get('id') or len(result) + 1}",
                kind="news",
                title=title[:300],
                source=str(source or "Yahoo Finance")[:100],
                observed_at=observed_at,
                available_at=available_at,
                summary=str(content.get("summary") or content.get("description") or "")[:800],
                url=str(url)[:1000],
            )
        )
    return result


def _load_ticker(candidates: tuple[str, ...]) -> tuple[str, Any, Any]:
    """후보 표기를 차례로 시도해 시세가 나오는 첫 번째를 채택한다.

    한국 종목은 접미사 없이 입력되는 일이 많아 .KS(코스피)와 .KQ(코스닥)를 모두 시도한다.
    """
    last_reason: Exception | None = None
    for candidate in candidates:
        ticker = yf.Ticker(candidate)
        try:
            history = ticker.history(period="1y", interval="1d", auto_adjust=True, timeout=15)
        # 공급자가 어떤 예외든 던질 수 있어 넓게 잡고 다음 후보로 넘어간다.
        except Exception as reason:
            last_reason = reason
            continue
        if not history.empty and "Close" in history:
            return candidate, ticker, history
    if last_reason is not None:
        raise MarketDataError(f"시장 데이터 조회에 실패했습니다: {last_reason}") from last_reason
    tried = ", ".join(candidates)
    raise MarketDataError(f"{tried} 시세를 찾을 수 없습니다. 거래소 티커를 확인해 주세요.")


def fetch_market_snapshot(
    symbol: str,
    *,
    news_errors: list[str] | None = None,
    news_loader: Callable[[Any, str], list[Evidence]] | None = None,
) -> tuple[MarketSnapshot, list[Evidence]]:
    """Yahoo Finance 공개 데이터로 현재 스냅샷과 AI 입력 근거를 만든다."""
    route = route_symbol(symbol)
    available_at = datetime.now(UTC).isoformat()
    normalized, ticker, history = _load_ticker(yfinance_candidates(route))
    try:
        info = ticker.info or {}
        financials, financial_period = _statement_values(ticker)
    except Exception as reason:
        raise MarketDataError(f"시장 데이터 조회에 실패했습니다: {reason}") from reason
    try:
        news = (
            news_loader(ticker, available_at)
            if news_loader
            else _news_evidence(ticker, available_at, limit=50)
        )
    except Exception:
        news = []
        if news_errors is not None:
            news_errors.append("Yahoo 종목 뉴스 조회 실패")

    closes = history["Close"].dropna()
    highs = history["High"].dropna()
    price = _finite(closes.iloc[-1])
    if price is None:
        raise MarketDataError(f"{normalized}의 최근 종가가 올바르지 않습니다.")

    daily_returns = closes.pct_change().dropna()
    volatility = _finite(daily_returns.tail(20).std() * math.sqrt(252) * 100)
    previous_close = closes.shift(1)
    true_range = (history["High"] - history["Low"]).to_frame("range")
    true_range["high_gap"] = (history["High"] - previous_close).abs()
    true_range["low_gap"] = (history["Low"] - previous_close).abs()
    atr = _finite(true_range.max(axis=1).tail(20).mean())
    rolling_peak = closes.cummax()
    max_drawdown = _finite(((closes / rolling_peak) - 1).min() * 100)
    high_52w = _finite(highs.max())
    distance_from_high = ((price / high_52w) - 1) * 100 if high_52w else None
    observed_at = history.index[-1].isoformat()
    averages = moving_averages(closes, price)
    chart_rows = [
        (
            index.isoformat() if hasattr(index, "isoformat") else str(index),
            _finite(row.get("Open")) or _finite(row.get("Close")) or 0.0,
            _finite(row.get("High")) or _finite(row.get("Close")) or 0.0,
            _finite(row.get("Low")) or _finite(row.get("Close")) or 0.0,
            _finite(row.get("Close")) or 0.0,
        )
        for index, row in history.iterrows()
    ]
    chart_points = price_chart_points(chart_rows)

    snapshot = MarketSnapshot(
        symbol=normalized,
        company=str(info.get("longName") or info.get("shortName") or normalized),
        exchange=str(info.get("fullExchangeName") or info.get("exchange") or ""),
        currency=str(info.get("currency") or ""),
        sector=str(info.get("sector") or ""),
        observed_at=observed_at,
        price=price,
        market_cap=_finite(info.get("marketCap")),
        return_1d_pct=_period_return(closes, 1),
        return_1m_pct=_period_return(closes, 21),
        return_6m_pct=_period_return(closes, 126),
        return_1y_pct=_window_return(closes),
        high_52w=high_52w,
        distance_from_high_pct=distance_from_high,
        volatility_20d_pct=volatility,
        atr_20=atr,
        moving_averages=averages,
        chart_points=chart_points,
        max_drawdown_1y_pct=max_drawdown,
        avg_volume_20d=_finite(history["Volume"].tail(20).mean()),
        beta=_finite(info.get("beta")),
        trailing_pe=_finite(info.get("trailingPE")),
        price_to_book=_finite(info.get("priceToBook")),
        revenue_growth_pct=_pct(info.get("revenueGrowth")),
        gross_margin_pct=_pct(info.get("grossMargins")),
        profit_margin_pct=_pct(info.get("profitMargins")),
        financial_period=financial_period,
        technical=technical_metrics(history["Close"].tolist(), history["Volume"].tolist()),
        financial_details=_financial_details(ticker, info),
        **financials,
    )
    market_summary = (
        f"종가 {price:.2f} {snapshot.currency}; 1일 {snapshot.return_1d_pct}; "
        f"1개월 {snapshot.return_1m_pct}; 6개월 {snapshot.return_6m_pct}; "
        f"1년 {snapshot.return_1y_pct}; 20일 연환산 변동성 {snapshot.volatility_20d_pct}; "
        f"1년 최대 낙폭 {snapshot.max_drawdown_1y_pct}; 베타 {snapshot.beta}; "
        f"시가총액 {snapshot.market_cap}; 20일선 {averages.ma_20}, 60일선 {averages.ma_60}, "
        f"100일선 {averages.ma_100}; 이평 배열 {averages.alignment}."
    )
    financial_summary = (
        "; ".join(f"{name}={value}" for name, value in financials.items() if value is not None)
        or "공개 재무제표 값을 가져오지 못함"
    )
    evidence = [
        Evidence(
            id="market:price-and-risk",
            kind="market",
            title=f"{normalized} 가격·수익률·위험 지표",
            source="Yahoo Finance",
            observed_at=observed_at,
            available_at=available_at,
            summary=market_summary,
        ),
        Evidence(
            id="financial:latest-annual",
            kind="financial",
            title=f"{normalized} 최근 연간 재무 스냅샷",
            source="Yahoo Finance",
            observed_at=financial_period or observed_at,
            available_at=available_at,
            summary=financial_summary,
        ),
        *news,
    ]
    return snapshot, evidence

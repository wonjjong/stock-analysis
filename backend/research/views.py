"""정량 랭커와 종목 AI 보고서를 연결하는 JSON API."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync, sync_to_async
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from news.models import NewsArticle
from research.analysis import Evidence, create_live_report, create_report
from research.dart_profile import account_evidence, parse_single_account
from research.forms import ApiTestForm, StockLabForm, StockRankForm
from research.macro import fetch_macro_regime
from research.market_data import MarketDataError, fetch_market_snapshot
from research.recommendation import Candidate, MacroRegime, rank_candidates
from research.scoring import FactorScores, score_snapshot
from research.sec_profile import build_filer_profile, profile_evidence
from research.services import (
    CompanyIndexError,
    DartApiError,
    DartClient,
    SecApiError,
    SecClient,
    resolve_kr_company,
    resolve_us_company,
)
from research.stock_search import search_symbols
from research.symbols import SymbolRoute, route_symbol

logger = logging.getLogger(__name__)

# 사업보고서 기준. DART 는 조회 연도의 보고서가 아직 없으면 013(데이터 없음)을 준다.
DART_ANNUAL_REPORT = "11011"


def _number(data: dict[str, Any], name: str, *, minimum: float | None = None) -> float:
    value = data.get(name)
    if isinstance(value, bool):
        raise ValueError(f"{name}은 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as reason:
        raise ValueError(f"{name}은 숫자여야 합니다.") from reason
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name}은 유한한 숫자여야 합니다.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name}은 {minimum} 이상이어야 합니다.")
    return number


def _candidate(raw: object) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError("candidates의 각 항목은 객체여야 합니다.")
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol or len(symbol) > 20:
        raise ValueError("각 후보에 올바른 symbol이 필요합니다.")
    return Candidate(
        symbol=symbol,
        price=_number(raw, "price", minimum=0),
        atr_20=_number(raw, "atr_20", minimum=0),
        quality=_number(raw, "quality"),
        value=_number(raw, "value"),
        momentum=_number(raw, "momentum"),
        revisions=_number(raw, "revisions"),
        news=_number(raw, "news"),
        liquidity=_number(raw, "liquidity", minimum=0),
        drawdown=_number(raw, "drawdown", minimum=0),
        beta=_number(raw, "beta"),
        stale_ratio=_number(raw, "stale_ratio", minimum=0),
    )


def _regime(raw: object) -> MacroRegime:
    if not isinstance(raw, dict):
        raise ValueError("regime 객체가 필요합니다.")
    return MacroRegime(
        vix=_number(raw, "vix", minimum=0),
        usdkrw_change_20d=_number(raw, "usdkrw_change_20d"),
        us10y_change_bp_20d=_number(raw, "us10y_change_bp_20d"),
        credit_spread_change_bp_20d=_number(raw, "credit_spread_change_bp_20d"),
    )


def _news_evidence(symbol: str, limit: int = 10) -> list[Evidence]:
    rows = (
        NewsArticle.objects.filter(symbols__symbol=symbol)
        .select_related("source", "insight")
        .distinct()
        .order_by("-published_at", "-id")[:limit]
    )
    evidence: list[Evidence] = []
    for article in rows:
        insight = getattr(article, "insight", None)
        observed = article.published_at or article.collected_at
        evidence.append(
            Evidence(
                id=f"news:{article.pk}",
                kind="news",
                title=article.title[:300],
                source=article.source.name,
                observed_at=observed.isoformat(),
                available_at=article.collected_at.isoformat(),
                summary=(insight.summary if insight else article.excerpt)[:800],
                url=article.canonical_url,
            )
        )
    return evidence


def _sentiment_scores(symbol: str, limit: int = 20) -> list[int]:
    """종목에 붙은 최근 기사의 감성 점수. 뉴스 팩터의 재료다."""
    code = symbol.split(".")[0]
    return list(
        NewsArticle.objects.filter(symbols__symbol=code)
        .exclude(insight__isnull=True)
        .order_by("-published_at", "-id")
        .values_list("insight__sentiment_score", flat=True)[:limit]
    )


def _score_symbols(symbols: list[str]) -> tuple[list[FactorScores], list[dict[str, str]]]:
    """종목마다 시세를 받아 팩터 점수를 만든다. 실패한 종목은 건너뛰고 이유를 남긴다."""
    scored: list[FactorScores] = []
    failures: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            snapshot, _ = fetch_market_snapshot(symbol)
        except MarketDataError as reason:
            failures.append({"symbol": symbol, "reason": str(reason)})
            continue
        scored.append(
            score_snapshot(snapshot.as_dict(), sentiment_scores=_sentiment_scores(snapshot.symbol))
        )
    return scored, failures


# rank_candidates 의 진입 조건. 여기 값이 바뀌면 recommendation.py 와 함께 고쳐야 한다.
MIN_LIQUIDITY_SCORE = 35
MAX_STALE_RATIO = 0.15


def _rejection_reason(scores: FactorScores) -> str:
    """정량 순위에서 빠진 이유를 사람이 읽을 수 있게 만든다."""
    if scores.price <= 0:
        return "가격 정보를 받지 못했습니다."
    if scores.liquidity < MIN_LIQUIDITY_SCORE:
        return f"거래대금이 기준에 미달합니다(유동성 점수 {scores.liquidity:.0f} < {MIN_LIQUIDITY_SCORE})."
    if scores.stale_ratio > MAX_STALE_RATIO:
        return f"시세 데이터가 너무 많이 비었습니다(결측 비율 {scores.stale_ratio:.0%})."
    return "정량 순위 기준을 통과하지 못했습니다."


def rank_stocks(request: HttpRequest):
    """여러 종목을 팩터 점수로 줄 세운다. 상위 종목은 AI 분석 화면으로 넘긴다."""
    ranked: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, int]] = {}
    failures: list[dict[str, str]] = []
    macro = None
    form = StockRankForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        scored, failures = _score_symbols(form.cleaned_data["symbols"])
        if not scored:
            form.add_error("symbols", "시세를 받은 종목이 없습니다. 티커를 확인해 주세요.")
        else:
            macro = fetch_macro_regime()
            candidates = [item.as_candidate() for item in scored]
            ranked = rank_candidates(candidates, macro.regime, len(candidates))
            coverage = {item.symbol: item.coverage for item in scored}
            # rank_candidates 는 기준 미달 종목을 조용히 버린다. 사용자가 6개를 넣었는데
            # 2개만 보이는 이유를 알 수 있게, 빠진 종목과 사유를 함께 넘긴다.
            survived = {row["symbol"] for row in ranked}
            failures += [
                {"symbol": item.symbol, "reason": _rejection_reason(item)}
                for item in scored
                if item.symbol not in survived
            ]
            if not ranked:
                form.add_error(
                    "symbols",
                    "유동성·데이터 신선도 기준을 통과한 종목이 없습니다. "
                    "거래대금이 크고 공개 데이터가 충실한 종목으로 시도해 주세요.",
                )
    return render(
        request,
        "research/rank.html",
        {
            "form": form,
            "ranked": ranked,
            "coverage": coverage,
            "failures": failures,
            "macro": macro.as_dict() if macro else None,
        },
    )


def stock_search(request: HttpRequest) -> JsonResponse:
    """종목 검색 자동완성. 국내는 KIS 종목마스터, 미국은 SEC 티커 목록을 본다.

    인증이 필요 없는 파일만 쓰므로 자격증명 없이 동작한다.
    """
    query = request.GET.get("q", "")[:40]
    return JsonResponse({"results": [choice.as_dict() for choice in search_symbols(query)]})


def _filing_evidence(route: SymbolRoute) -> list[Evidence]:
    """공시 근거를 붙인다. 시세는 필수지만 공시는 보조라 어떤 실패도 분석을 막지 않는다.

    async_to_sync 는 여기서만 쓴다. WSGI 동기 뷰라 실행 중인 이벤트 루프가 없어 안전하고,
    이 한 곳 덕분에 클라이언트에 동기 메서드를 복제하지 않아도 된다.
    """
    available_at = datetime.now(UTC).isoformat()
    try:
        if route.market == "US":
            company = resolve_us_company(route.base)
            submissions = async_to_sync(SecClient().get_company_submissions)(company.key)
            return profile_evidence(build_filer_profile(submissions), available_at)

        company = resolve_kr_company(route.base)
        # 사업보고서는 이듬해 3월경 공시되므로 직전 연도를 조회한다.
        year = str(datetime.now(UTC).year - 1)
        payload = async_to_sync(DartClient().get_financial_statement)(
            corp_code=company.key, year=year, reprt_code=DART_ANNUAL_REPORT
        )
        accounts = parse_single_account(payload)
        return account_evidence(company, accounts, year, DART_ANNUAL_REPORT, available_at)
    except (CompanyIndexError, DartApiError, SecApiError) as reason:
        logger.info("공시 근거를 붙이지 못했습니다 (%s): %s", route.symbol, reason)
        return []


def stock_lab(request: HttpRequest):
    """임의 티커의 공개 시장 데이터를 수집하고 등록된 AI 공급자로 분석한다."""
    result = None
    evidence: list[Evidence] = []
    attempts: list[dict[str, str]] = []
    # 랭킹 표에서 'AI 분석 →' 로 넘어오면 종목이 쿼리스트링에 실려 온다.
    initial = {"symbol": request.GET["symbol"]} if request.GET.get("symbol") else None
    form = StockLabForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        symbol = form.cleaned_data["symbol"]
        try:
            snapshot, evidence = fetch_market_snapshot(symbol)
            evidence = [*evidence, *_filing_evidence(route_symbol(symbol))]
            report, attempts = create_live_report(snapshot.as_dict(), evidence)
            result = {"snapshot": snapshot, "report": report}
        except MarketDataError as reason:
            form.add_error("symbol", str(reason))
    return render(
        request,
        "research/lab.html",
        {
            "form": form,
            "result": result,
            "evidence": evidence,
            "attempts": attempts,
        },
    )


async def api_test(request: HttpRequest):
    """티커·종목코드로 DART/SEC 를 조회하고 원본 응답을 확인하는 테스트 화면."""
    result = None
    company = None
    form = ApiTestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = form.cleaned_data["service"]
        identifier = form.cleaned_data["identifier"]
        year = form.cleaned_data.get("year") or "2023"

        # 인덱스 조회는 sync 라 스레드로 뺀다. thread_sensitive=True 면 직렬화돼 이득이 없다.
        resolve = sync_to_async(
            resolve_kr_company if service == "DART" else resolve_us_company,
            thread_sensitive=False,
        )
        try:
            company = await resolve(identifier)
            if service == "DART":
                result = await DartClient().get_financial_statement(corp_code=company.key, year=year)
            else:
                result = await SecClient().get_company_facts(cik=company.key)
        except (CompanyIndexError, DartApiError, SecApiError) as reason:
            form.add_error("identifier", str(reason))

    return render(
        request,
        "research/api_test.html",
        {
            "form": form,
            "company": company,
            "result": json.dumps(result, indent=2, ensure_ascii=False) if result is not None else None,
        },
    )


@csrf_exempt
@require_POST
def analyze_stock(request: HttpRequest, symbol: str) -> JsonResponse:
    """후보군을 정량 순위화한 뒤 해당 종목을 같은 시점의 뉴스 근거와 함께 AI가 해석한다.

    ## CSRF 를 면제하는 이유
    브라우저 폼이 아니라 프로그램이 호출하는 JSON API 라 토큰을 실을 주체가 없다. 이 뷰는
    조회와 계산만 하고 DB 를 바꾸지 않으므로, CSRF 가 막으려는 '남의 세션으로 상태를
    변경당하는' 위험 자체가 없다.

    다만 시세 조회와 LLM 호출이 붙어 있어 **호출당 비용이 든다**. 공개 배포한다면 인증이나
    호출 한도를 앞에 두어야 한다. 화면에서 쓰는 rank_stocks/stock_lab 은 폼 뷰라 CSRF 보호를
    그대로 유지한다.
    """
    try:
        payload = json.loads(request.body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("요청 본문은 JSON 객체여야 합니다.")
        # symbols 를 주면 서버가 시세를 받아 팩터 점수를 직접 만든다. candidates 를 주면
        # 그 값을 그대로 쓴다(기존 계약 유지). 둘 다 없으면 오류다.
        raw_symbols = payload.get("symbols")
        if isinstance(raw_symbols, list) and raw_symbols:
            if len(raw_symbols) > StockRankForm.MAX_SYMBOLS:
                raise ValueError(f"symbols 는 한 번에 {StockRankForm.MAX_SYMBOLS}개까지 계산합니다.")
            scored, _ = _score_symbols([str(item).strip().upper() for item in raw_symbols])
            if not scored:
                raise ValueError("시세를 받은 종목이 없습니다.")
            candidates = [item.as_candidate() for item in scored]
            regime = fetch_macro_regime().regime
        else:
            raw_candidates = payload.get("candidates")
            if not isinstance(raw_candidates, list) or not raw_candidates:
                raise ValueError("symbols 배열 또는 candidates 배열이 필요합니다.")
            if len(raw_candidates) > 5000:
                raise ValueError("후보 종목은 한 번에 5000개까지 분석할 수 있습니다.")
            candidates = [_candidate(item) for item in raw_candidates]
            regime = _regime(payload.get("regime"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as reason:
        return JsonResponse({"error": str(reason)}, status=400)

    normalized_symbol = symbol.strip().upper()
    recommendations = rank_candidates(candidates, regime, len(candidates))
    recommendation = next((item for item in recommendations if item["symbol"] == normalized_symbol), None)
    if recommendation is None:
        return JsonResponse({"error": "유동성·데이터 신선도 기준을 통과한 분석 대상이 아닙니다."}, status=422)

    candidate = next(item for item in candidates if item.symbol == normalized_symbol)
    evidence = _news_evidence(normalized_symbol)
    report, attempts = create_report(
        recommendation,
        asdict(candidate),
        asdict(regime),
        evidence,
    )
    return JsonResponse(
        {
            "recommendation": recommendation,
            "report": report.as_dict(),
            "evidence": [asdict(item) for item in evidence],
            "providerAttempts": attempts,
        }
    )

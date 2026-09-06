"""SEC 등록사 티커 → CIK 인덱스.

이 파일은 data.sec.gov 가 아니라 **www.sec.gov** 에 있어 SecClient 의 엔드포인트 헬퍼를
쓸 수 없다. 다만 SEC 입장에서는 같은 클라이언트이므로 레이트리밋 게이트는 공유한다.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from news.crawler.symbols import lookup_symbol
from research.services.company_index import (
    BaseCompanyIndex,
    CompanyIndex,
    CompanyIndexError,
    CompanyRef,
    build_name_map,
    normalize_ticker,
)
from research.services.rate_limit import SEC_GATE
from research.services.sec import WWW_BASE_URL, sec_headers

logger = logging.getLogger(__name__)

TICKERS_URL = f"{WWW_BASE_URL}/files/company_tickers.json"
# 실측 797KB. news/crawler/fetcher.py 의 상한 관례를 따른다.
MAX_INDEX_BYTES = 8_000_000
# 부분 응답이 멀쩡한 인덱스를 덮어쓰는 사고를 막는 하한(실측 10,412건).
MIN_EXPECTED_ROWS = 1_000
DOWNLOAD_TIMEOUT = 30.0


def parse_company_tickers(blob: bytes) -> CompanyIndex:
    """company_tickers.json 바이트를 CompanyIndex 로 만든다. 네트워크가 없는 순수 함수다.

    입력 형태: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
    바깥 키는 단순 일련번호라 의미가 없어 values() 만 쓴다.

    CIK 는 여기서 한 번만 10자리로 채운다. SecClient 가 다시 zfill(10) 을 해도 멱등이라
    기존 시그니처를 바꾸지 않아도 된다.
    """
    try:
        payload = json.loads(blob)
    except ValueError as reason:
        raise CompanyIndexError(f"SEC 티커 목록을 JSON 으로 읽지 못했습니다: {reason}") from reason

    if isinstance(payload, dict):
        rows: list[object] = list(payload.values())
    elif isinstance(payload, list):
        rows = payload
    else:
        raise CompanyIndexError("SEC 티커 목록의 형식이 예상과 다릅니다.")

    # 같은 CIK 를 여러 티커가 공유한다(BRK-A/BRK-B). 별칭을 채우려면 두 번 훑어야 한다.
    staged: list[tuple[str, str, str]] = []
    tickers_by_cik: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = normalize_ticker(str(row.get("ticker") or ""))
        cik_raw = str(row.get("cik_str") or "").strip()
        if not ticker or not cik_raw.isdigit() or int(cik_raw) == 0:
            continue
        cik = cik_raw.zfill(10)
        staged.append((ticker, cik, str(row.get("title") or "").strip()))
        tickers_by_cik.setdefault(cik, []).append(ticker)

    if len(staged) < MIN_EXPECTED_ROWS:
        raise CompanyIndexError(f"SEC 티커 목록이 비정상적으로 짧습니다({len(staged)}건). 갱신을 건너뜁니다.")

    by_ticker: dict[str, CompanyRef] = {}
    by_key: dict[str, CompanyRef] = {}
    as_of = time.strftime("%Y-%m-%d")
    for ticker, cik, title in staged:
        ref = CompanyRef(
            market="US",
            key=cik,
            ticker=ticker,
            name=title,
            name_en=title,
            aliases=tuple(t for t in tickers_by_cik[cik] if t != ticker),
            source="SEC company_tickers.json",
            as_of=as_of,
        )
        by_ticker[ticker] = ref
        # 대표 티커는 파일에 먼저 나온 것으로 둔다.
        by_key.setdefault(cik, ref)

    return CompanyIndex(
        as_of=as_of,
        built_at=time.time(),
        by_ticker=by_ticker,
        by_key=by_key,
        by_name=build_name_map(list(by_key.values())),
    )


class SecTickerIndex(BaseCompanyIndex):
    market = "US"
    cache_key = "research:sec:ticker-index"
    source_label = "SEC company_tickers.json"

    def _fetch(self) -> bytes:
        SEC_GATE.wait()
        try:
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                response = client.get(TICKERS_URL, headers=sec_headers())
                response.raise_for_status()
                blob = response.content
        except httpx.HTTPError as reason:
            raise CompanyIndexError(f"SEC 티커 목록을 받지 못했습니다: {reason}") from reason
        if len(blob) > MAX_INDEX_BYTES:
            raise CompanyIndexError(f"SEC 티커 목록이 상한({MAX_INDEX_BYTES}바이트)을 넘었습니다.")
        return blob

    def _parse(self, blob: bytes) -> CompanyIndex:
        return parse_company_tickers(blob)

    def _lookup_key(self, query: str) -> str | None:
        """숫자만 들어오면 CIK 직접 입력으로 본다(기존 화면 하위호환)."""
        return query.zfill(10) if query.isdigit() else None

    def _alias_ticker(self, query: str) -> str | None:
        """news 앱의 종목 사전을 별칭 계층으로 빌려 쓴다.

        corpCode.xml / company_tickers.json 에는 정식 사명만 있어 '삼바'·'한전'·'엔비디아'
        같은 통칭이나 옛 사명(대우조선해양 → 한화오션)으로는 찾을 수 없다. 뉴스 매칭용으로
        이미 관리하는 사전이 그 별칭을 갖고 있으므로 새로 만들지 않고 재사용한다.
        """
        entry = lookup_symbol(query)
        return entry.symbol if entry is not None and entry.market == "US" else None

    def _describe_miss(self, query: str, index: CompanyIndex) -> str:
        # 이 목록에는 EDGAR 에 직접 등록·보고하는 발행사만 들어간다. SPY·TSM 처럼 스스로
        # 보고하는 ETF·ADR 은 있지만, 상위 신탁의 개별 시리즈(VOO)나 비후원 ADR(NSRGY),
        # 미국에 등록하지 않은 해외 법인은 빠진다.
        return (
            f"'{query}' 는 SEC 등록 티커 목록({len(index.by_ticker):,}건)에 없습니다. "
            "EDGAR 에 직접 보고하지 않는 종목(펀드의 개별 시리즈, 비후원 ADR, "
            "미국에 등록하지 않은 해외 법인, 미국 외 거래소 상장 종목)은 포함되지 않습니다."
            + self.suggest(query)
        )


sec_index = SecTickerIndex()


def resolve_us_company(query: str) -> CompanyRef:
    """티커 또는 CIK 로 미국 등록사를 찾는다. 실패하면 CompanyNotFound."""
    return sec_index.resolve(query)

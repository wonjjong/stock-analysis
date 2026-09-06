"""한국투자증권 종목마스터 → 국내 상장 종목 목록.

## dart_index 와 역할이 다르다
dart_index 는 '공시를 찾기 위한 corp_code 다리'다. 여기 필요한 것은 **사용자가 고를 수 있는
종목 목록**이라 성격이 다르다. 종목마스터에는 거래소 구분, 증권 그룹(주권 vs ETF/ETN/리츠),
거래정지 여부, 시가총액 규모가 있어 후보를 제대로 추릴 수 있다.

## 인증이 필요 없다
종목마스터는 KIS 다운로드 서버에서 그냥 받는다. appkey/appsecret 없이도 종목 검색이
동작하고, 시세 조회 단계에서만 자격증명이 필요하다.

## 포맷
cp949 고정폭이다. 각 행의 **뒤에서** 상세 블록(코스피 227자, 코스닥 221자)을 떼면 그 앞이
단축코드(9) + 표준코드(12) + 한글명(가변)이다. KIS 참조 스크립트는 줄바꿈이 붙은 행에서
228/222 자를 떼므로, 줄바꿈을 먼저 제거하는 여기서는 1 이 작다.

오프셋은 참조 스크립트(stocks_info/kis_*_code_mst.py)의 field_specs 누적값이다. 눈으로
세면 틀리므로(실제로 처음에 틀렸다) 값을 바꿀 때는 그 스크립트에서 다시 계산할 것.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from dataclasses import dataclass

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

logger = logging.getLogger(__name__)

MASTER_URL = "https://new.real.download.dws.co.kr/common/master/{name}_code.mst.zip"
# 증권그룹구분코드. ST(주권) 외에는 분석 대상이 아니다(EF=ETF, EN=ETN, RT=리츠, DR=예탁증서…).
COMMON_STOCK_GROUP = "ST"
MAX_ARCHIVE_BYTES = 10_000_000
MIN_EXPECTED_ROWS = 500
DOWNLOAD_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class MasterSpec:
    """시장별 종목마스터 레이아웃."""

    name: str  # 다운로드 파일 이름(kospi/kosdaq)
    exchange: str
    tail_width: int
    group: tuple[int, int]
    size: tuple[int, int]
    halted: tuple[int, int]
    preferred: tuple[int, int]
    market_cap: tuple[int, int]


# 시가총액은 두 시장 모두 억원 단위 9자리다(코스닥 컬럼명에 '(억)' 이 명시돼 있고,
# 코스피도 같은 단위로 정렬 순서가 맞는다). 절대값을 표시하지는 않고 정렬에만 쓴다.
MASTER_SPECS = (
    MasterSpec("kospi", "KOSPI", 227, (0, 2), (2, 3), (60, 61), (158, 159), (212, 221)),
    MasterSpec("kosdaq", "KOSDAQ", 221, (0, 2), (2, 3), (55, 56), (153, 154), (206, 215)),
)

# 보통주 → 우선주 → 스팩 순으로 민다. 시가총액만으로 정렬하면 '삼성' 검색에 삼성전자우가
# 삼성바이오로직스보다 앞에 오는데, 분석 대상으로는 보통주가 먼저여야 한다.
COMMON_TIER, PREFERRED_TIER, SPAC_TIER = 0, 1, 2

# 코스피 SPAC 필드는 전 종목이 N 이라 쓸 수 없어 종목명으로 판별한다.
SPAC_MARKERS = ("스팩", "기업인수목적")


def _tier(preferred_code: str, name: str) -> int:
    """자동완성에서 어느 묶음에 넣을지. 작을수록 먼저 보여 준다."""
    if any(marker in name for marker in SPAC_MARKERS):
        return SPAC_TIER
    return PREFERRED_TIER if preferred_code not in ("", "0") else COMMON_TIER


def parse_master(blob: bytes, spec: MasterSpec) -> list[CompanyRef]:
    """종목마스터 ZIP 에서 거래 가능한 보통주만 뽑는다. 네트워크가 없는 순수 함수다."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
        members = [name for name in archive.namelist() if name.lower().endswith(".mst")]
        if not members:
            raise CompanyIndexError(f"{spec.exchange} 종목마스터 ZIP 안에 .mst 가 없습니다.")
        text = archive.read(members[0]).decode("cp949", "replace")
    except zipfile.BadZipFile as reason:
        raise CompanyIndexError(f"{spec.exchange} 종목마스터가 ZIP 이 아닙니다: {reason}") from reason

    refs: list[CompanyRef] = []
    as_of = time.strftime("%Y-%m-%d")
    for line in text.splitlines():
        if len(line) <= spec.tail_width + 21:
            continue
        tail = line[-spec.tail_width :]
        if tail[spec.group[0] : spec.group[1]].strip() != COMMON_STOCK_GROUP:
            continue
        if tail[spec.halted[0] : spec.halted[1]].strip() == "Y":
            continue
        code = normalize_ticker(line[:9])
        name = line[21 : len(line) - spec.tail_width].strip()
        if not code or not name:
            continue
        preferred = tail[spec.preferred[0] : spec.preferred[1]].strip()
        cap = tail[spec.market_cap[0] : spec.market_cap[1]].strip()
        refs.append(
            CompanyRef(
                market="KR",
                key=code,
                ticker=code,
                name=name,
                source=f"KIS 종목마스터({spec.exchange})",
                as_of=as_of,
                exchange=spec.exchange,
                rank_hint=_tier(preferred, name),
                market_cap=int(cap) if cap.isdigit() else 0,
            )
        )
    return refs


class KisStockIndex(BaseCompanyIndex):
    """코스피·코스닥 보통주 목록. 종목 검색 자동완성의 근거다."""

    market = "KR"
    cache_key = "research:kis:stock-index"
    source_label = "KIS 종목마스터"

    def _fetch(self) -> bytes:  # pragma: no cover - _build_index 가 시장별로 받는다
        raise NotImplementedError

    def _parse(self, blob: bytes) -> CompanyIndex:  # pragma: no cover - 위와 같다
        raise NotImplementedError

    def _fetch_market(self, spec: MasterSpec) -> bytes:
        if self._downloader is not None:
            return self._downloader()
        try:
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                response = client.get(MASTER_URL.format(name=spec.name))
                response.raise_for_status()
                blob = response.content
        except httpx.HTTPError as reason:
            raise CompanyIndexError(f"{spec.exchange} 종목마스터를 받지 못했습니다: {reason}") from reason
        if len(blob) > MAX_ARCHIVE_BYTES:
            raise CompanyIndexError(f"{spec.exchange} 종목마스터가 상한을 넘었습니다.")
        return blob

    def _build_index(self) -> CompanyIndex:
        """코스피와 코스닥을 각각 받아 하나로 합친다."""
        refs: list[CompanyRef] = []
        for spec in MASTER_SPECS:
            refs.extend(parse_master(self._fetch_market(spec), spec))
        if len(refs) < MIN_EXPECTED_ROWS:
            raise CompanyIndexError(f"종목마스터가 비정상적으로 짧습니다({len(refs)}건). 갱신을 건너뜁니다.")
        by_ticker = {ref.ticker: ref for ref in refs}
        return CompanyIndex(
            as_of=time.strftime("%Y-%m-%d"),
            built_at=time.time(),
            by_ticker=by_ticker,
            by_key=dict(by_ticker),
            by_name=build_name_map(refs),
        )

    def _lookup_key(self, query: str) -> str | None:
        return query if query.isdigit() and len(query) == 6 else None

    def _alias_ticker(self, query: str) -> str | None:
        """news 앱 종목 사전의 통칭·옛 사명을 빌려 쓴다('한전' → 015760)."""
        entry = lookup_symbol(query)
        return entry.symbol if entry is not None and entry.market == "KR" else None

    def _describe_miss(self, query: str, index: CompanyIndex) -> str:
        return (
            f"'{query}' 를 국내 상장 종목({len(index.by_ticker):,}건)에서 찾지 못했습니다. "
            "ETF·ETN·리츠와 거래정지 종목은 목록에서 제외됩니다." + self.suggest(query)
        )


kis_index = KisStockIndex()


def search_kr_stocks(query: str, limit: int = 10) -> list[CompanyRef]:
    """국내 종목 자동완성. 인증이 필요 없어 자격증명 없이도 동작한다."""
    return kis_index.autocomplete(query, limit)

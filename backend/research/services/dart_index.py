"""DART 종목코드/회사명 → corp_code 인덱스.

## corpCode.xml 은 JSON 이 아니다
Content-Type 이 application/x-msdownload 로 오지만 실체는 ZIP(멤버 CORPCODE.xml 하나)이다.
그래서 DartClient._request(JSON 파싱 + status 검사)를 재사용할 수 없다. 키가 틀리면 ZIP 도
아닌 평문 XML(<result><status>013</status></result>)이 오므로 BadZipFile 을 만나면 그
XML 을 해석해 사람이 읽을 수 있는 메시지로 바꾼다.

## 상장사만 인덱싱한다
전체 118,852건 중 stock_code 가 있는 상장사는 3,988건뿐이다. 나머지 비상장·폐지 법인은
회사명 충돌만 늘리고 LocMemCache 에는 워커당 수십 MB 부담이다. 이 프로젝트는 상장 종목
분석기이므로 상장사만 남긴다.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from xml.etree import ElementTree

import httpx
from django.conf import settings

from news.crawler.symbols import lookup_symbol
from research.services.company_index import (
    BaseCompanyIndex,
    CompanyIndex,
    CompanyIndexError,
    CompanyRef,
    build_name_map,
    format_yyyymmdd,
    normalize_ticker,
)
from research.services.dart import BASE_URL, describe_status

logger = logging.getLogger(__name__)

CORP_CODE_URL = f"{BASE_URL}/corpCode.xml"
# 실측 3.6MB.
MAX_ARCHIVE_BYTES = 20_000_000
# 압축 해제 크기 상한(zip bomb 가드). 실측 XML 은 약 20MB 다.
MAX_XML_BYTES = 100_000_000
MIN_EXPECTED_ROWS = 100
DOWNLOAD_TIMEOUT = 60.0


def _dart_error_from_xml(blob: bytes) -> str | None:
    """ZIP 이 아닌 응답에서 DART 상태 코드를 읽어 낸다. 해석할 수 없으면 None."""
    try:
        root = ElementTree.fromstring(blob.decode("utf-8", "replace"))
    except ElementTree.ParseError:
        return None
    status = (root.findtext("status") or "").strip()
    if not status:
        return None
    return describe_status(status, (root.findtext("message") or "").strip())


def _read_archive(blob: bytes) -> bytes:
    """ZIP 에서 CORPCODE.xml 바이트를 꺼낸다. ZIP 이 아니면 DART 오류로 번역한다."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as reason:
        message = _dart_error_from_xml(blob)
        raise CompanyIndexError(message or f"DART 회사 목록이 ZIP 이 아닙니다: {reason}") from reason

    members = [info for info in archive.infolist() if info.filename.lower().endswith(".xml")]
    if not members:
        raise CompanyIndexError("DART 회사 목록 ZIP 안에 XML 이 없습니다.")
    member = members[0]
    if member.file_size > MAX_XML_BYTES:
        raise CompanyIndexError(f"DART 회사 목록이 상한({MAX_XML_BYTES}바이트)을 넘었습니다.")
    return archive.read(member)


def parse_corp_code_archive(blob: bytes, *, listed_only: bool = True) -> CompanyIndex:
    """corpCode ZIP 바이트를 CompanyIndex 로 만든다. stdlib 만 쓰는 순수 함수다."""
    try:
        root = ElementTree.fromstring(_read_archive(blob).decode("utf-8", "replace"))
    except ElementTree.ParseError as reason:
        raise CompanyIndexError(f"DART 회사 목록 XML 을 읽지 못했습니다: {reason}") from reason

    refs: list[CompanyRef] = []
    modify_dates: list[str] = []
    for entry in root.iter("list"):
        corp_code = (entry.findtext("corp_code") or "").strip()
        stock_code = normalize_ticker(entry.findtext("stock_code") or "")
        if not corp_code or (listed_only and not stock_code):
            continue
        modify_date = (entry.findtext("modify_date") or "").strip()
        if modify_date:
            modify_dates.append(modify_date)
        refs.append(
            CompanyRef(
                market="KR",
                key=corp_code,
                ticker=stock_code,
                name=(entry.findtext("corp_name") or "").strip(),
                name_en=(entry.findtext("corp_eng_name") or "").strip(),
                source="DART corpCode.xml",
                as_of=format_yyyymmdd(modify_date),
            )
        )

    if len(refs) < MIN_EXPECTED_ROWS:
        raise CompanyIndexError(f"DART 회사 목록이 비정상적으로 짧습니다({len(refs)}건). 갱신을 건너뜁니다.")

    as_of = format_yyyymmdd(max(modify_dates, default=""))
    by_ticker: dict[str, CompanyRef] = {}
    by_key: dict[str, CompanyRef] = {}
    for ref in refs:
        if ref.ticker:
            by_ticker[ref.ticker] = ref
        by_key.setdefault(ref.key, ref)

    return CompanyIndex(
        as_of=as_of,
        built_at=time.time(),
        by_ticker=by_ticker,
        by_key=by_key,
        by_name=build_name_map(refs),
    )


class DartCorpIndex(BaseCompanyIndex):
    market = "KR"
    cache_key = "research:dart:corp-index"
    source_label = "DART corpCode.xml"

    def _fetch(self) -> bytes:
        api_key = getattr(settings, "SIGNALIST_DART_API_KEY", "")
        if not api_key:
            raise CompanyIndexError("DART API 키가 없습니다. SIGNALIST_DART_API_KEY 를 설정하세요.")
        try:
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                response = client.get(CORP_CODE_URL, params={"crtfc_key": api_key})
                response.raise_for_status()
                blob = response.content
        except httpx.HTTPError as reason:
            raise CompanyIndexError(f"DART 회사 목록을 받지 못했습니다: {reason}") from reason
        if len(blob) > MAX_ARCHIVE_BYTES:
            raise CompanyIndexError(f"DART 회사 목록이 상한({MAX_ARCHIVE_BYTES}바이트)을 넘었습니다.")
        return blob

    def _parse(self, blob: bytes) -> CompanyIndex:
        return parse_corp_code_archive(blob, listed_only=True)

    def _lookup_key(self, query: str) -> str | None:
        """corp_code 는 8자리다. 6자리 숫자는 종목코드이므로 by_ticker 로 넘긴다."""
        return query if query.isdigit() and len(query) == 8 else None

    def _alias_ticker(self, query: str) -> str | None:
        """news 앱의 종목 사전을 별칭 계층으로 빌려 쓴다.

        corpCode.xml / company_tickers.json 에는 정식 사명만 있어 '삼바'·'한전'·'엔비디아'
        같은 통칭이나 옛 사명(대우조선해양 → 한화오션)으로는 찾을 수 없다. 뉴스 매칭용으로
        이미 관리하는 사전이 그 별칭을 갖고 있으므로 새로 만들지 않고 재사용한다.
        """
        entry = lookup_symbol(query)
        return entry.symbol if entry is not None and entry.market == "KR" else None

    def _describe_miss(self, query: str, index: CompanyIndex) -> str:
        return (
            f"'{query}' 는 DART 상장사 목록({len(index.by_ticker):,}건)에 없습니다. "
            "종목코드(6자리) 또는 정확한 회사명으로 입력해 주세요." + self.suggest(query)
        )


dart_index = DartCorpIndex()


def resolve_kr_company(query: str) -> CompanyRef:
    """종목코드(005930·005930.KS)·회사명(삼성전자)·corp_code 로 한국 상장사를 찾는다."""
    return dart_index.resolve(query)

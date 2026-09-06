"""인덱스 파서와 식별자 정규화 검증. 네트워크를 타지 않는다."""

from __future__ import annotations

import io
import json
import time
import zipfile

import pytest
from django.core.cache import cache

from research.services.company_index import (
    CompanyIndexError,
    CompanyNotFound,
    normalize_name,
    ticker_variants,
)
from research.services.dart_index import DartCorpIndex, parse_corp_code_archive
from research.services.sec_index import SecTickerIndex, parse_company_tickers

# 실제 응답과 같은 모양: 바깥 키가 문자열 일련번호, cik_str 은 int.
SEC_ROWS = [
    {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    {"cik_str": 1878848, "ticker": "IREN", "title": "IREN Ltd"},
    {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
    {"cik_str": 1067983, "ticker": "BRK-A", "title": "BERKSHIRE HATHAWAY INC"},
]

DART_ROWS = [
    ("00126380", "삼성전자", "SAMSUNG ELECTRONICS CO,.LTD", "005930", "20251201"),
    ("00877059", "삼성바이오로직스", "", "207940", "20250801"),
    ("00111704", "한화오션", "", "042660", "20250701"),
    ("00164779", "SK하이닉스", "SK hynix Inc.", "000660", "20250901"),
    ("00999999", "비상장법인", "", "", "20240101"),
]


def _sec_blob(rows: list[dict] | None = None, *, count: int = 1200) -> bytes:
    """MIN_EXPECTED_ROWS 를 넘기려고 더미 행으로 채운다."""
    entries = list(rows if rows is not None else SEC_ROWS)
    for index in range(count):
        entries.append({"cik_str": 9000000 + index, "ticker": f"ZZ{index}", "title": f"FILLER {index}"})
    return json.dumps({str(i): row for i, row in enumerate(entries)}).encode()


def _dart_blob(rows: list[tuple[str, str, str, str, str]] | None = None, *, count: int = 200) -> bytes:
    entries = list(rows if rows is not None else DART_ROWS)
    for index in range(count):
        entries.append((f"1{index:07d}", f"더미{index}", "", f"9{index:05d}", "20250101"))
    body = "".join(
        "<list>"
        f"<corp_code>{code}</corp_code><corp_name>{name}</corp_name>"
        f"<corp_eng_name>{eng}</corp_eng_name><stock_code>{stock}</stock_code>"
        f"<modify_date>{modified}</modify_date>"
        "</list>"
        for code, name, eng, stock, modified in entries
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CORPCODE.xml", f"<result>{body}</result>")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# --- 정규화 ---


def test_ticker_variants_covers_class_share_notation():
    assert ticker_variants(" brk.b ")[:3] == ("BRK.B", "BRK-B", "BRKB")


def test_ticker_variants_strips_exchange_suffix():
    assert "005930" in ticker_variants("005930.KS")


def test_normalize_name_drops_legal_form_suffixes():
    assert normalize_name("삼성전자(주)") == normalize_name("삼성전자")
    assert normalize_name("NVIDIA CORP") == normalize_name("nvidia")


# --- SEC 파서 ---


def test_parse_company_tickers_pads_cik_to_ten_digits():
    index = parse_company_tickers(_sec_blob())
    assert index.by_ticker["NVDA"].key == "0001045810"
    assert index.by_ticker["IREN"].key == "0001878848"


def test_shared_cik_links_class_shares_as_aliases():
    index = parse_company_tickers(_sec_blob())
    assert index.by_ticker["BRK-B"].aliases == ("BRK-A",)
    assert index.by_ticker["BRK-A"].key == index.by_ticker["BRK-B"].key


def test_short_payload_is_rejected_so_it_cannot_overwrite_a_good_index():
    with pytest.raises(CompanyIndexError, match="비정상적으로 짧습니다"):
        parse_company_tickers(_sec_blob(count=0))


def test_malformed_json_raises_company_index_error():
    with pytest.raises(CompanyIndexError, match="JSON"):
        parse_company_tickers(b"not json")


# --- SEC 해결 ---


def _sec_resolver() -> SecTickerIndex:
    return SecTickerIndex(downloader=_sec_blob)


def test_ticker_cik_and_padded_cik_resolve_to_the_same_company():
    index = _sec_resolver()
    by_ticker = index.resolve("nvda")
    assert index.resolve("1045810") == by_ticker
    assert index.resolve("0001045810") == by_ticker


def test_dotted_class_share_resolves_through_variants():
    assert _sec_resolver().resolve("brk.b").ticker == "BRK-B"


def test_unlisted_symbol_explains_why_it_is_absent():
    # SPY 처럼 스스로 EDGAR 에 보고하는 ETF 는 실제 목록에 있다. 여기서는 픽스처에 없는
    # 표기를 골라, 미등재일 때 안내문이 이유를 설명하는지만 본다.
    with pytest.raises(CompanyNotFound, match="EDGAR 에 직접 보고하지 않는"):
        _sec_resolver().resolve("NSRGY")


# --- DART 파서 ---


def test_parse_corp_code_keeps_listed_companies_only():
    index = parse_corp_code_archive(_dart_blob())
    assert index.by_ticker["005930"].key == "00126380"
    assert "00999999" not in index.by_key


def test_as_of_is_the_latest_modify_date():
    assert parse_corp_code_archive(_dart_blob()).as_of == "2025-12-01"


def test_plain_xml_error_response_is_translated_to_dart_message():
    blob = b"<result><status>013</status><message>no data</message></result>"
    with pytest.raises(CompanyIndexError, match="조회된 데이터가 없습니다"):
        parse_corp_code_archive(blob)


def test_non_zip_binary_reports_a_readable_error():
    with pytest.raises(CompanyIndexError, match="ZIP"):
        parse_corp_code_archive(b"\x00\x01\x02 not a zip")


# --- DART 해결 ---


def _dart_resolver() -> DartCorpIndex:
    return DartCorpIndex(downloader=_dart_blob)


def test_stock_code_corp_code_and_company_name_resolve_to_the_same_company():
    index = _dart_resolver()
    expected = index.resolve("005930")
    assert expected.key == "00126380"
    assert index.resolve("00126380") == expected
    assert index.resolve("삼성전자") == expected


def test_yfinance_suffix_is_stripped_before_lookup():
    assert _dart_resolver().resolve("005930.KS").key == "00126380"


def test_unknown_korean_query_suggests_candidates():
    with pytest.raises(CompanyNotFound, match="DART 상장사 목록"):
        _dart_resolver().resolve("존재하지않는회사")


# --- 캐시 동작 ---


class _CountingIndex(SecTickerIndex):
    """다운로드 횟수를 세는 인덱스. 캐시 동작 검증 전용이다."""

    cache_key = "research:test:counting-index"

    def __init__(self, *, fail_after: int | None = None) -> None:
        super().__init__()
        self.calls = 0
        self.fail_after = fail_after

    def _fetch(self) -> bytes:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise CompanyIndexError("의도적인 다운로드 실패")
        return _sec_blob()


def test_second_load_is_served_from_cache_without_downloading_again():
    index = _CountingIndex()
    index.load()
    index.load()
    assert index.calls == 1


def test_stale_index_is_served_when_refresh_fails():
    index = _CountingIndex(fail_after=1)
    fresh = index.load()

    # built_at 을 과거로 심는다. time.time 을 패치하는 것보다 견고하다.
    stale = type(fresh)(
        as_of=fresh.as_of,
        built_at=time.time() - 10 * 24 * 3600,
        by_ticker=fresh.by_ticker,
        by_key=fresh.by_key,
        by_name=fresh.by_name,
    )
    cache.set(index._versioned_key, stale, 3600)

    assert stale.is_stale
    assert index.load().by_ticker["NVDA"].key == "0001045810"
    assert index.calls == 2


def test_download_failure_without_cache_raises():
    index = _CountingIndex(fail_after=0)
    with pytest.raises(CompanyIndexError, match="의도적인 다운로드 실패"):
        index.load()


# --- 별칭 계층 (news 앱 종목 사전 재사용) ---


def test_korean_nickname_resolves_through_the_shared_symbol_dictionary():
    """corpCode.xml 에는 정식 사명만 있어 '삼바' 로는 못 찾는다. 사전이 그 간극을 메운다."""
    assert _dart_resolver().resolve("삼바").key == "00877059"


def test_former_company_name_still_resolves():
    """대우조선해양 → 한화오션. 옛 사명으로 들어온 질의도 현재 법인을 찾아야 한다."""
    company = _dart_resolver().resolve("대우조선해양")
    assert (company.key, company.name) == ("00111704", "한화오션")


def test_korean_nickname_for_us_stock_resolves_to_cik():
    assert _sec_resolver().resolve("엔비디아").key == "0001045810"


def test_alias_layer_does_not_override_an_exact_ticker_match():
    """별칭은 마지막 폴백이다. 정식 티커·사명이 맞으면 그쪽이 이긴다."""
    assert _sec_resolver().resolve("AAPL").key == "0000320193"


# --- 회사명 정규화 (자동완성 정확도의 토대) ---


def test_legal_suffix_is_only_stripped_at_the_end():
    """'NVDA' 안의 nv, 'CODA' 안의 co 를 지우면 엉뚱한 회사가 매치된다(실제로 그랬다)."""
    assert normalize_name("NVDA") == "NVDA"
    assert normalize_name("CODA") == "CODA"


def test_trailing_legal_suffixes_are_stripped():
    assert normalize_name("Apple Inc.") == normalize_name("apple")
    assert normalize_name("NVIDIA CORP") == normalize_name("nvidia")
    assert normalize_name("IREN Ltd") == normalize_name("iren")


def test_exact_ticker_beats_name_substring():
    """'NVDA' 검색에 이름이 비슷한 다른 회사가 먼저 오면 안 된다."""
    hits = _sec_resolver().autocomplete("NVDA", limit=3)
    assert hits[0].ticker == "NVDA"

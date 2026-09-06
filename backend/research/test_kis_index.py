"""KIS 종목마스터 파서와 자동완성 검증. 네트워크를 타지 않는다."""

from __future__ import annotations

import io
import zipfile

import pytest
from django.core.cache import cache

from research.services.company_index import CompanyNotFound
from research.services.kis_index import MASTER_SPECS, KisStockIndex, MasterSpec, parse_master

KOSPI = MASTER_SPECS[0]


def _row(
    spec: MasterSpec,
    code: str,
    name: str,
    *,
    group: str = "ST",
    size: str = "1",
    halted: str = "N",
    preferred: str = "0",
    cap: int = 1000,
) -> str:
    """종목마스터 한 행을 만든다. 상세 블록은 정확히 tail_width 자여야 한다."""
    tail = [" "] * spec.tail_width

    def put(bounds: tuple[int, int], value: str) -> None:
        start, stop = bounds
        padded = value.rjust(stop - start)[: stop - start]
        tail[start:stop] = list(padded)

    put(spec.group, group)
    put(spec.size, size)
    put(spec.halted, halted)
    put(spec.preferred, preferred)
    put(spec.market_cap, str(cap).zfill(spec.market_cap[1] - spec.market_cap[0]))
    return code.ljust(9) + f"KR7{code}003".ljust(12) + name + "".join(tail)


def _archive(spec: MasterSpec, rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{spec.name}_code.mst", "\n".join(rows).encode("cp949"))
    return buffer.getvalue()


def _kospi(rows: list[str]) -> bytes:
    return _archive(KOSPI, rows)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_common_stock_is_parsed_with_code_and_name():
    refs = parse_master(_kospi([_row(KOSPI, "005930", "삼성전자")]), KOSPI)
    assert (refs[0].ticker, refs[0].name, refs[0].exchange) == ("005930", "삼성전자", "KOSPI")


def test_etf_and_etn_are_excluded_because_they_are_not_analysis_targets():
    rows = [_row(KOSPI, "005930", "삼성전자"), _row(KOSPI, "069500", "KODEX 200", group="EF")]
    assert [ref.ticker for ref in parse_master(_kospi(rows), KOSPI)] == ["005930"]


def test_halted_stock_is_excluded():
    rows = [_row(KOSPI, "005930", "삼성전자"), _row(KOSPI, "999999", "거래정지주", halted="Y")]
    assert [ref.ticker for ref in parse_master(_kospi(rows), KOSPI)] == ["005930"]


def test_market_cap_is_read_for_ordering():
    refs = parse_master(_kospi([_row(KOSPI, "005930", "삼성전자", cap=14615696)]), KOSPI)
    assert refs[0].market_cap == 14615696


def test_preferred_share_and_spac_are_tiered_behind_common_stock():
    rows = [
        _row(KOSPI, "005930", "삼성전자"),
        _row(KOSPI, "005935", "삼성전자우", preferred="1"),
        _row(KOSPI, "0115H0", "삼성스팩13호"),
    ]
    tiers = {ref.name: ref.rank_hint for ref in parse_master(_kospi(rows), KOSPI)}
    assert tiers["삼성전자"] < tiers["삼성전자우"] < tiers["삼성스팩13호"]


def test_corrupt_archive_reports_a_readable_error():
    from research.services.company_index import CompanyIndexError

    with pytest.raises(CompanyIndexError, match="ZIP"):
        parse_master(b"not a zip at all", KOSPI)


# --- 자동완성 ---


def _index() -> KisStockIndex:
    rows = [
        _row(KOSPI, "005930", "삼성전자", cap=14615696),
        _row(KOSPI, "005935", "삼성전자우", preferred="1", cap=1477165),
        _row(KOSPI, "207940", "삼성바이오로직스", cap=683717),
        _row(KOSPI, "0115H0", "삼성스팩13호", cap=100),
        _row(KOSPI, "035720", "카카오", cap=156600),
    ]
    # 최소 건수 검증을 통과시키려고 더미로 채운다.
    rows += [_row(KOSPI, f"9{i:05d}", f"더미{i}", cap=i) for i in range(600)]
    blob = _kospi(rows)
    index = KisStockIndex(downloader=lambda: blob)
    # 두 시장을 각각 받으므로 같은 blob 이 두 번 파싱된다. 코스닥 스펙과는 폭이 달라
    # 대부분 걸러지지만, 검증에는 영향이 없다.
    return index


def test_prefix_match_puts_the_largest_common_stock_first():
    """'삼성' 을 치면 삼성전자가 먼저다. 우선주·스팩이 앞에 오면 안 된다."""
    names = [ref.name for ref in _index().autocomplete("삼성", limit=3)]
    assert names[0] == "삼성전자"
    assert "삼성스팩13호" not in names


def test_stock_code_prefix_matches():
    assert _index().autocomplete("00593", limit=5)[0].ticker == "005930"


def test_empty_query_returns_nothing():
    assert _index().autocomplete("   ") == []


def test_unknown_query_explains_that_etfs_are_excluded():
    with pytest.raises(CompanyNotFound, match="ETF·ETN·리츠와 거래정지"):
        _index().resolve("존재하지않는종목명")

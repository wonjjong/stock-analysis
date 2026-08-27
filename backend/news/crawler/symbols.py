"""
종목 매칭. `app/lib/symbol-dictionary.ts` 의 matchSymbols / lookupSymbol 이식.
사전 데이터는 `symbol_data.py`(기계 생성)에 있다.

## 이 로직이 조심하는 것들

- **긴 별칭을 먼저 센다.** `카카오뱅크` 기사가 `카카오` 로 중복 집계되지 않게, 매치한
  별칭을 스캔 대상에서 지워 가며 진행한다.
- **노이즈 문구를 먼저 제거한다.** 공유 버튼의 `카카오톡` 이 종목 `카카오` 로 잡히면 안 된다.
- **영문 티커는 단어 경계를 요구한다.** `ARM` 이 `alarm` 에 걸리는 오탐을 막는다.
  JS 는 lookbehind/lookahead 를 쓰는데 Python `re` 도 고정폭이라 그대로 이식된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .symbol_data import NOISE_TERMS, SYMBOL_DICTIONARY, SymbolEntry

# JS: /^[\x20-\x7E]+$/ — 출력 가능한 ASCII 만으로 이루어진 별칭(영문 티커·사명)
_LATIN = re.compile(r"^[\x20-\x7e]+$")
_JS_ESCAPE = re.compile(r"[.*+?^${}()|\[\]\\]")

MAX_MATCHES = 8


@dataclass(slots=True)
class SymbolMatch:
    symbol: str
    company: str
    market: str
    sector: str
    mentions: int
    relevance: int
    match_type: str = "사전"

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "company": self.company,
            "market": self.market,
            "sector": self.sector,
            "mentions": self.mentions,
            "relevance": self.relevance,
            "matchType": self.match_type,
        }


def occurrences(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    if _LATIN.match(needle):
        escaped = _JS_ESCAPE.sub(lambda m: "\\" + m.group(0), needle)
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE
        )
        return len(pattern.findall(haystack))
    # 한글 별칭은 겹치지 않게 needle 길이만큼 건너뛰며 센다(JS 구현과 같다).
    count = 0
    index = haystack.find(needle)
    while index >= 0:
        count += 1
        index = haystack.find(needle, index + len(needle))
    return count


def match_symbols(title: str, body: str) -> list[SymbolMatch]:
    pairs: list[tuple[SymbolEntry, str]] = [
        (entry, alias) for entry in SYMBOL_DICTIONARY for alias in entry.aliases
    ]
    # 긴 별칭 우선. 안정 정렬이라 같은 길이면 사전 순서가 유지된다(JS 와 동일).
    pairs.sort(key=lambda pair: len(pair[1]), reverse=True)

    scan_title, scan_body = title, body
    for noise in NOISE_TERMS:
        scan_title = " ".join(scan_title.split(noise))
        scan_body = " ".join(scan_body.split(noise))

    found: dict[str, SymbolMatch] = {}
    for entry, alias in pairs:
        in_title = occurrences(scan_title, alias)
        in_body = occurrences(scan_body, alias)
        if not in_title and not in_body:
            continue
        if in_title:
            scan_title = " ".join(scan_title.split(alias))
        if in_body:
            scan_body = " ".join(scan_body.split(alias))
        mentions = in_title + in_body
        relevance = max(0, min(100, (72 if in_title else 40) + min(mentions * 6, 28)))
        existing = found.get(entry.symbol)
        if existing:
            existing.mentions += mentions
            existing.relevance = max(existing.relevance, relevance)
            continue
        found[entry.symbol] = SymbolMatch(
            entry.symbol, entry.name, entry.market, entry.sector, mentions, relevance
        )

    matches = list(found.values())
    matches.sort(key=lambda m: (m.relevance, m.mentions), reverse=True)
    return matches[:MAX_MATCHES]


def lookup_symbol(value: str) -> SymbolEntry | None:
    needle = value.strip().lower()
    for entry in SYMBOL_DICTIONARY:
        if (
            entry.symbol.lower() == needle
            or entry.name.lower() == needle
            or any(alias.lower() == needle for alias in entry.aliases)
        ):
            return entry
    return None

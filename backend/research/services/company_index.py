"""사람이 읽는 식별자(티커·종목코드·회사명)를 기관 식별자(CIK·corp_code)로 바꾼다.

SEC 와 DART 는 배포 형식만 다르고(JSON vs ZIP+XML) 파이프라인이 같다:
전량 파일 다운로드 → 파싱 → 인덱싱 → 캐시 → 정규화 질의 → 폴백.
그 공통부를 여기 두고 하위 클래스는 URL 과 파서만 제공한다.

## 왜 stale 을 그냥 버리지 않는가
원본 파일은 하루 한 번 갱신되는 수 MB 짜리다. 갱신에 실패했다고 조회 자체를 막으면
SEC 가 잠깐 막힌 동안 화면 전체가 죽는다. 논리 TTL(하루)이 지나면 갱신을 시도하되,
실패하면 캐시 TTL(일주일) 안의 낡은 인덱스를 그대로 쓴다.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from django.core.cache import cache

logger = logging.getLogger(__name__)

# 캐시에 담는 dataclass 모양이 바뀌면 올린다. 옛 pickle 이 TypeError 로 터지는 것을 막는다.
CACHE_SCHEMA_VERSION = 3
LOGICAL_TTL_SECONDS = 24 * 3600
CACHE_TTL_SECONDS = 7 * 24 * 3600

# 다른 워커가 같은 파일을 받는 동안 중복 다운로드를 막는다(공유 캐시 백엔드가 있을 때만 효과).
DOWNLOAD_LOCK_SECONDS = 120

# 회사명 비교에서 떼어 낼 법인 형태 접미사.
_NAME_KR_NOISE = re.compile(r"주식회사|\(주\)|㈜")
# 영문 법인 형태는 **맨 뒤 토큰일 때만** 뗀다. 경계 없이 지우면 'NVDA' 에서 nv 가,
# 'CODA' 에서 co 가 사라져 엉뚱한 회사가 매치된다(실제로 그랬다).
_NAME_EN_SUFFIX = re.compile(
    r"[,\s]+(inc|corp|corporation|co|company|ltd|limited|plc|holdings?|group)\.?$",
    re.IGNORECASE,
)
_NAME_PUNCT = re.compile(r"[\s.,\-_/&'\"]+")


class CompanyIndexError(RuntimeError):
    """인덱스 구축 실패. 메시지가 폼 에러로 그대로 노출된다."""


class CompanyNotFound(CompanyIndexError):
    """질의에 해당하는 회사를 인덱스에서 찾지 못했다."""


@dataclass(frozen=True, slots=True)
class CompanyRef:
    """시장 중립적인 회사 참조. SEC/DART 어느 쪽이든 같은 모양으로 나온다."""

    market: str
    key: str
    ticker: str
    name: str
    name_en: str = ""
    aliases: tuple[str, ...] = ()
    source: str = ""
    as_of: str = ""
    exchange: str = ""  # "KOSPI" | "KOSDAQ" | "Nasdaq" …
    # 자동완성 정렬용. rank_hint 는 작을수록, market_cap(억원)은 클수록 먼저 보여 준다.
    rank_hint: int = 0
    market_cap: int = 0


@dataclass(frozen=True, slots=True)
class CompanyIndex:
    """캐시에 통째로 들어가는 조회 테이블."""

    as_of: str
    built_at: float
    by_ticker: dict[str, CompanyRef]
    by_key: dict[str, CompanyRef]
    by_name: dict[str, tuple[str, ...]] = field(default_factory=dict)
    schema: int = CACHE_SCHEMA_VERSION

    @property
    def is_stale(self) -> bool:
        return time.time() - self.built_at > LOGICAL_TTL_SECONDS

    def __len__(self) -> int:
        return len(self.by_key)


def normalize_ticker(value: str) -> str:
    """공백을 없애고 대문자로 만든다. 표기 변형은 ticker_variants 가 맡는다."""
    return "".join(value.split()).upper()


def ticker_variants(value: str) -> tuple[str, ...]:
    """같은 종목의 표기 변형을 우선순위대로 낸다. 첫 히트를 채택하므로 순서가 곧 우선순위다.

    예: 'brk.b' → ('BRK.B', 'BRK-B', 'BRKB'), '005930.KS' → ('005930.KS', '005930')
    """
    base = normalize_ticker(value)
    if not base:
        return ()
    seen: list[str] = []
    for candidate in (
        base,
        base.replace(".", "-"),
        base.replace("-", "."),
        base.replace(".", "").replace("-", ""),
        base.rsplit(".", 1)[0] if "." in base else base,
    ):
        if candidate and candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def normalize_name(value: str) -> str:
    """회사명 비교용 정규화. 대소문자·공백·구두점·법인 형태 접미사를 지운다."""
    cleaned = _NAME_KR_NOISE.sub("", value).strip()
    # 'X Holdings Corp' 처럼 겹친 접미사도 벗긴다.
    while True:
        trimmed = _NAME_EN_SUFFIX.sub("", cleaned)
        if trimmed == cleaned:
            break
        cleaned = trimmed
    return _NAME_PUNCT.sub("", cleaned).upper()


def format_yyyymmdd(value: str) -> str:
    """DART 의 modify_date(YYYYMMDD)를 ISO 표기로. 형식이 다르면 그대로 둔다."""
    digits = value.strip()
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) == 8 and digits.isdigit() else digits


def build_name_map(refs: list[CompanyRef]) -> dict[str, tuple[str, ...]]:
    """정규화 회사명 → key 목록. 동명이 있으면 목록이 2건 이상이 되어 resolve 가 거절한다."""
    result: dict[str, list[str]] = {}
    for ref in refs:
        for raw in (ref.name, ref.name_en):
            key = normalize_name(raw)
            if not key:
                continue
            bucket = result.setdefault(key, [])
            if ref.key not in bucket:
                bucket.append(ref.key)
    return {name: tuple(keys) for name, keys in result.items()}


class BaseCompanyIndex(ABC):
    """전량 파일을 받아 캐시하는 인덱스의 공통 골격."""

    market: ClassVar[str]
    cache_key: ClassVar[str]
    source_label: ClassVar[str]

    def __init__(self, downloader: Callable[[], bytes] | None = None) -> None:
        self._downloader = downloader
        self._lock = threading.Lock()

    # --- 하위 클래스가 채우는 부분 ---

    @abstractmethod
    def _fetch(self) -> bytes:
        """원본 파일 바이트를 받는다. 네트워크가 닿는 유일한 지점."""

    @abstractmethod
    def _parse(self, blob: bytes) -> CompanyIndex:
        """바이트 → CompanyIndex. 순수 함수여야 하며 테스트가 여기를 직접 친다."""

    @abstractmethod
    def _describe_miss(self, query: str, index: CompanyIndex) -> str:
        """조회 실패 안내문. 시장마다 빠지는 대상이 달라서 하위 클래스가 쓴다."""

    # --- 공통 동작 ---

    @property
    def _versioned_key(self) -> str:
        return f"{self.cache_key}:v{CACHE_SCHEMA_VERSION}"

    def _download(self) -> bytes:
        return self._downloader() if self._downloader is not None else self._fetch()

    def _cached(self) -> CompanyIndex | None:
        cached = cache.get(self._versioned_key)
        if isinstance(cached, CompanyIndex) and cached.schema == CACHE_SCHEMA_VERSION:
            return cached
        return None

    def _build_index(self) -> CompanyIndex:
        """원본을 받아 인덱스를 만든다. 원본이 여러 파일인 인덱스는 이 메서드를 갈아끼운다."""
        return self._parse(self._download())

    def _rebuild(self) -> CompanyIndex:
        index = self._build_index()
        cache.set(self._versioned_key, index, CACHE_TTL_SECONDS)
        logger.info(
            "%s 인덱스를 갱신했습니다: 회사 %d건 / 티커 %d건 (기준일 %s)",
            self.source_label,
            len(index),
            len(index.by_ticker),
            index.as_of,
        )
        return index

    def load(self, *, force: bool = False) -> CompanyIndex:
        """캐시 우선. stale 이면 갱신을 시도하고, 실패하면 stale 을 그대로 돌려준다."""
        cached = None if force else self._cached()
        if cached is not None and not cached.is_stale:
            return cached

        # 다른 스레드가 이미 받는 중이면 낡은 값이라도 즉시 준다.
        if not self._lock.acquire(blocking=cached is None):
            return cached if cached is not None else self.load(force=force)
        try:
            fresh = self._cached()
            if not force and fresh is not None and not fresh.is_stale:
                return fresh
            lock_key = f"{self._versioned_key}:lock"
            if cached is not None and not cache.add(lock_key, 1, DOWNLOAD_LOCK_SECONDS):
                return cached
            try:
                return self._rebuild()
            except CompanyIndexError:
                if cached is None:
                    raise
                logger.warning("%s 인덱스 갱신에 실패해 이전 인덱스를 사용합니다.", self.source_label)
                return cached
            finally:
                cache.delete(lock_key)
        finally:
            self._lock.release()

    def _lookup_key(self, query: str) -> str | None:
        """숫자로만 이루어진 질의를 기관 식별자로 해석한다. 하위 클래스가 자릿수를 맞춘다."""
        return query if query.isdigit() else None

    def _alias_ticker(self, query: str) -> str | None:
        """공식 사명으로 못 찾았을 때 쓸 별칭 → 티커. 기본은 없음."""
        return None

    def resolve(self, query: str) -> CompanyRef:
        """티커·종목코드·기관 식별자·회사명 순으로 찾는다. 실패하면 CompanyNotFound."""
        cleaned = query.strip()
        if not cleaned:
            raise CompanyNotFound("종목 식별자를 입력해 주세요.")

        index = self.load()

        direct = self._lookup_key(cleaned)
        if direct and direct in index.by_key:
            return index.by_key[direct]

        for variant in ticker_variants(cleaned):
            found = index.by_ticker.get(variant)
            if found is not None:
                return found

        keys = index.by_name.get(normalize_name(cleaned), ())
        if len(keys) == 1:
            return index.by_key[keys[0]]
        if len(keys) > 1:
            names = ", ".join(f"{index.by_key[k].name}({index.by_key[k].ticker})" for k in keys[:5])
            raise CompanyNotFound(
                f"'{cleaned}' 와 이름이 같은 회사가 여럿입니다. 종목코드로 지정해 주세요: {names}"
            )

        alias = self._alias_ticker(cleaned)
        if alias:
            for variant in ticker_variants(alias):
                found = index.by_ticker.get(variant)
                if found is not None:
                    return found

        partial = self.search(cleaned, limit=2)
        if len(partial) == 1:
            return partial[0]

        raise CompanyNotFound(self._describe_miss(cleaned, index))

    def search(self, query: str, limit: int = 10) -> list[CompanyRef]:
        """회사명 부분 일치 검색. 자동완성과 오타 안내에 쓴다."""
        needle = normalize_name(query)
        if not needle:
            return []
        index = self.load()
        result: list[CompanyRef] = []
        for name, keys in index.by_name.items():
            if needle in name:
                for key in keys:
                    ref = index.by_key.get(key)
                    if ref is not None and ref not in result:
                        result.append(ref)
                        if len(result) >= limit:
                            return result
        return result

    def autocomplete(self, query: str, limit: int = 10) -> list[CompanyRef]:
        """종목명·코드로 후보를 낸다.

        티커 완전일치 > 티커 앞자리 > 이름 앞자리 > 이름 포함 순이고, 같은 순위 안에서는
        보통주를 우선주·스팩보다 앞에 두고 시가총액이 큰 것을 먼저 보여 준다.
        """
        raw = query.strip()
        if not raw:
            return []
        index = self.load()
        needle = normalize_name(raw)
        code = normalize_ticker(raw)
        # '테슬라' 처럼 공시기관 목록에 없는 통칭은 별칭 사전으로 티커를 찾아 준다.
        alias = self._alias_ticker(raw)

        scored: list[tuple[tuple[int, int, int, int], CompanyRef]] = []
        for ref in index.by_ticker.values():
            name = normalize_name(ref.name)
            # 티커 완전 일치가 최우선이다. 'NVDA' 로 검색해 NVIDIA 가 아닌 회사가
            # 이름 부분일치로 먼저 나오면 안 된다.
            if (code and ref.ticker == code) or (alias and ref.ticker == alias):
                priority = 0
            elif code and ref.ticker.startswith(code):
                priority = 1
            elif needle and name.startswith(needle):
                priority = 2
            elif needle and needle in name:
                priority = 3
            else:
                continue
            # 시가총액이 없는 인덱스(SEC)에서는 이름이 짧을수록 가까운 매치다.
            # 'apple' 검색에 Apple Hospitality REIT 가 Apple Inc. 보다 앞서면 안 된다.
            scored.append(((priority, ref.rank_hint, -ref.market_cap, len(ref.name)), ref))
        scored.sort(key=lambda item: item[0])
        return [ref for _, ref in scored[:limit]]

    def suggest(self, query: str, limit: int = 5) -> str:
        """조회 실패 안내에 붙일 후보 문자열. 후보가 없으면 빈 문자열."""
        candidates = self.search(query, limit=limit)
        if not candidates:
            return ""
        listed = ", ".join(f"{ref.name}({ref.ticker})" for ref in candidates)
        return f" 혹시 이건가요? {listed}"

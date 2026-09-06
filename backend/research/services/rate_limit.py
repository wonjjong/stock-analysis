"""외부 API 호출 간 최소 간격을 강제하는 게이트.

SEC EDGAR 는 IP 당 초당 10건을 공식 상한으로 두고, 넘기면 403 또는 429 를 준다.
클라이언트마다 따로 세면 의미가 없으므로 도메인 단위 게이트를 모듈 상수로 공유한다.

sync/async 양쪽 대기 메서드를 두는 이유: SecClient 는 async 이고 인덱스 다운로더는
sync 인데, SEC 입장에서는 같은 클라이언트라 같은 게이트를 지나야 한다.
"""

from __future__ import annotations

import asyncio
import threading
import time


class RateGate:
    """호출 간 최소 간격을 보장한다. 프로세스 로컬이라 워커가 여러 개면 IP 기준 상한을
    넘길 수 있으나, 그 경우는 호출부의 429 재시도가 흡수한다."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._next_at = 0.0
        self._lock = threading.Lock()
        self._async_lock: asyncio.Lock | None = None

    def _reserve(self) -> float:
        """다음 슬롯을 예약하고 그때까지 기다려야 할 시간을 돌려준다."""
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.min_interval
        return wait

    def wait(self) -> None:
        """동기 호출부에서 슬롯을 얻을 때까지 블로킹한다."""
        wait = self._reserve()
        if wait > 0:
            time.sleep(wait)

    async def await_slot(self) -> None:
        """비동기 호출부용. 예약은 스레드 락으로 하고 대기만 이벤트 루프에 양보한다."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        async with self._async_lock:
            wait = self._reserve()
            if wait > 0:
                await asyncio.sleep(wait)


# SEC 공식 상한은 초당 10건이다. 여유를 두어 8건으로 잡는다.
SEC_GATE = RateGate(min_interval=1 / 8)

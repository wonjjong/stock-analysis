"""
주기 실행. `scripts/scheduler.mjs` 를 대체한다.

Worker 에는 상시 프로세스가 없어 플랫폼이 매시 깨워 주었다. 여기서는 프로세스가 계속
살아 있으므로 직접 주기를 돈다. 소스별 실행 시각은 예전과 같이
`news_sources.next_crawl_at` 이 관리하므로 여기서는 기한이 된 소스를 자주 확인만 한다.

Celery 를 쓰지 않는 이유: 지수 백오프 재시도·2000종목 fan-out·복수 cadence 가 실제로
필요해질 때까지 브로커를 두지 않는다. 소스 몇 개를 위해 워커·비트·Redis 를 띄우는 것은
이 프로젝트의 Python 프로토타입을 죽인 바로 그 패턴이다.

프로덕션에서는 이것 대신 systemd timer 나 cron 으로 `crawl_news` · `analyze_news` 를
직접 부르는 편이 단순하다.
"""

from __future__ import annotations

import signal
import time
from typing import Any

from django.core.management.base import BaseCommand

from news.services.ingest import crawl_due_sources, reap_stuck_runs
from news.services.insights import process_pending_insights


class Command(BaseCommand):
    help = "기한이 된 소스 수집과 본문 분석을 주기적으로 실행합니다."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--interval", type=int, default=60, help="tick 간격(초)")
        parser.add_argument("--batch", type=int, default=20, help="tick 당 본문 분석 건수")
        parser.add_argument("--once", action="store_true", help="한 번만 실행하고 종료")

    def handle(self, *args: Any, **options: Any) -> None:
        interval = max(10, options["interval"])
        stopping = False

        def stop(*_: object) -> None:
            nonlocal stopping
            stopping = True
            self.stdout.write("종료 신호를 받았습니다. 현재 tick 을 마치고 멈춥니다.")

        for name in (signal.SIGINT, signal.SIGTERM):
            signal.signal(name, stop)

        while not stopping:
            self._tick(options["batch"])
            if options["once"] or stopping:
                break
            # 남은 시간을 잘게 쪼개 자야 종료 신호에 빠르게 반응한다.
            for _ in range(interval):
                if stopping:
                    break
                time.sleep(1)

    def _tick(self, batch: int) -> None:
        closed = reap_stuck_runs()
        if closed:
            self.stdout.write(self.style.WARNING(f"멈춰 있던 실행 {closed}건을 닫았습니다."))

        crawled = crawl_due_sources()
        if crawled:
            total = sum(r.inserted_count for r in crawled)
            self.stdout.write(f"수집 {len(crawled)}개 소스, 신규 {total}건")

        insights = process_pending_insights(batch)
        if insights.picked:
            self.stdout.write(
                f"본문 분석 {insights.done}/{insights.picked}"
                f" (LLM {insights.llm} · 규칙 {insights.rule} · 실패 {insights.failed})"
            )

        if not crawled and not insights.picked:
            self.stdout.write("기한이 된 소스와 대기 기사가 없습니다.")

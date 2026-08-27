"""기한이 된 소스를 수집한다. Worker cron 과 `scripts/scheduler.mjs` 의 절반을 대체."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from news.crawler.fetcher import CrawlError
from news.services.ingest import DUE_LIMIT, crawl_due_sources, crawl_source


class Command(BaseCommand):
    help = "기한이 된 뉴스 소스를 수집합니다. --source 로 하나만 지정할 수 있습니다."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--source", type=int, help="소스 ID 하나만 수집")
        parser.add_argument(
            "--limit", type=int, default=DUE_LIMIT, help=f"최대 소스 수 (기본 {DUE_LIMIT})"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["source"]:
            try:
                result = crawl_source(options["source"])
            except CrawlError as reason:
                raise CommandError(str(reason)) from reason
            self.stdout.write(
                self.style.SUCCESS(
                    f"{result.status} — {result.fetched_count}건 확인,"
                    f" 신규 {result.inserted_count}건"
                )
            )
            return

        results = crawl_due_sources(options["limit"])
        if not results:
            self.stdout.write("기한이 된 소스가 없습니다.")
            return

        for result in results:
            line = (
                f"소스 {result.source_id}: {result.status}"
                f" — {result.fetched_count}건 확인, 신규 {result.inserted_count}건"
            )
            if result.error:
                self.stdout.write(self.style.ERROR(f"소스 {result.source_id}: {result.error}"))
            else:
                self.stdout.write(line)

        total = sum(r.inserted_count for r in results)
        failed = sum(1 for r in results if r.error)
        self.stdout.write(
            self.style.SUCCESS(f"소스 {len(results)}개, 신규 {total}건, 실패 {failed}개")
        )

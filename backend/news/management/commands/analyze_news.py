"""대기 중인 기사의 본문을 분석한다. 스케줄러의 나머지 절반."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from news.services.insights import DEFAULT_BATCH, insight_queue_stats, process_pending_insights


class Command(BaseCommand):
    help = "대기 중인 기사의 본문을 분석합니다."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--limit", type=int, default=DEFAULT_BATCH,
            help=f"이번에 처리할 기사 수 (기본 {DEFAULT_BATCH})",
        )
        parser.add_argument("--stats", action="store_true", help="큐 현황만 출력")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["stats"]:
            stats = insight_queue_stats()
            self.stdout.write(
                f"대기 {stats['pending']} · 완료 {stats['done']} · 오류 {stats['failed']}"
            )
            self.stdout.write(f"엔진별: {stats['engines']}")
            configured = "예" if stats["llmConfigured"] else "아니오 (규칙 기반만)"
            self.stdout.write(f"LLM 설정됨: {configured}")
            return

        summary = process_pending_insights(options["limit"])
        if not summary.picked:
            self.stdout.write("대기 중인 기사가 없습니다.")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary.picked}건 중 {summary.done}건 완료"
                f" (LLM {summary.llm} · 규칙 {summary.rule} · 실패 {summary.failed})"
            )
        )
        if summary.providers:
            self.stdout.write(f"공급자별: {summary.providers}")

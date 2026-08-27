"""크롤러가 주고받는 값. Django 모델과 무관한 순수 자료구조다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedItem:
    title: str
    url: str
    excerpt: str
    # 정수 밀리초. 파서 전체가 이 도메인이고 datetime 변환은 DB 경계에서 한 번만 한다.
    published_at: int | None

    def as_dict(self) -> dict[str, object]:
        """정답지(JSON)와 비교할 때 쓰는 camelCase 형태."""
        return {
            "title": self.title,
            "url": self.url,
            "excerpt": self.excerpt,
            "publishedAt": self.published_at,
        }


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """수집에 필요한 소스 설정만 담는다(DB 행 전체가 아니다)."""

    id: int
    url: str
    resolved_url: str | None
    max_pages: int
    window_hours: int
    etag: str | None
    last_modified: str | None

    @property
    def target(self) -> str:
        return self.resolved_url or self.url

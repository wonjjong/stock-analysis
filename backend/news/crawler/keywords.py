"""
키워드 추출. `app/lib/keywords.ts` 이식. 형태소 분석기 없이 조사만 떼어 빈도로 뽑는다.

정렬 규칙이 미묘하다 — 가중치 내림차순, 동률이면 `localeCompare` 오름차순. Python 의
문자열 비교는 코드포인트 순서라 한글에서는 결과가 같다(ICU 로케일 정렬과 달라질 수 있는
지점이지만 정답지로 확인했다).
"""

from __future__ import annotations

import re

PARTICLES = ["으로써", "에서는", "으로는", "이라고", "라고는", "에게서", "으로", "에서",
             "에는", "과는", "와는", "이나", "까지", "부터", "보다", "처럼", "만큼", "라고",
             "이라", "에도", "에게", "한테", "이다", "하다", "했다", "된다", "됐다", "이라는",
             "라는", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "과", "와",
             "로", "야", "요"]

STOPWORDS = frozenset([
    "기자", "연합뉴스", "뉴스", "사진", "제공", "지난해", "올해", "내년", "지난", "이날",
    "관련", "대한", "위해", "통해", "따르면", "밝혔다", "말했다", "전했다", "대해", "가운데",
    "지난달", "이번", "당시", "현재", "최근", "오전", "오후", "서울", "기준", "경우", "가장",
    "모두", "다시", "함께", "이후", "이상", "이하", "그러나", "하지만", "때문", "라며",
    "면서", "무단", "전재", "배포", "금지", "저작권", "구독", "댓글", "그리고", "또한",
    "예정", "계획", "발표", "설명",
    "the", "and", "for", "with", "from", "that", "this", "has", "have", "was", "were",
    "will", "its", "inc", "corp", "ltd", "said", "says", "filed", "filer", "file", "type",
    "act", "size", "item", "year", "end", "state", "reuters", "bloomberg", "read", "more",
    "news",
])

_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z가-힣%]+")
_ENDS_HANGUL = re.compile(r"[가-힣]$")
_ALL_DIGITS = re.compile(r"^\d+$", re.ASCII)
_ALL_LATIN = re.compile(r"^[A-Za-z]+$")


def strip_particle(token: str) -> str:
    if not _ENDS_HANGUL.search(token):
        return token
    for particle in PARTICLES:
        if len(token) > len(particle) + 1 and token.endswith(particle):
            return token[: -len(particle)]
    return token


def extract_keywords(title: str, body: str, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}

    def scan(text: str, weight: int) -> None:
        for raw in _TOKEN_SPLIT.split(text):
            if len(raw) < 2:
                continue
            token = strip_particle(raw)
            if len(token) < 2 or len(token) > 20:
                continue
            if token.lower() in STOPWORDS:
                continue
            if _ALL_DIGITS.match(token):
                continue
            # 짧은 영문 토막은 대부분 약어·조각이라 버린다.
            if _ALL_LATIN.match(token) and len(token) < 4:
                continue
            counts[token] = counts.get(token, 0) + weight

    # 제목에 나온 말이 기사 주제일 확률이 높아 가중치를 크게 준다.
    scan(title, 4)
    scan(body, 1)

    ranked = [(token, count) for token, count in counts.items() if count > 1]
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return [token for token, _ in ranked[:limit]]

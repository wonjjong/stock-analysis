"""
텍스트 정리. `app/lib/news-crawler.ts` 의 decodeXml / cleanText / tag 이식.

Django 를 import 하지 않는다. 이 패키지는 순수 함수만 담고, DB 접근은 services 층이 한다.
"""

from __future__ import annotations

import re

# JS 의 `\s` 와 Python 의 `\s` 는 집합이 다르다. JS 는 U+FEFF(BOM)를 공백으로 보고
# Python 은 보지 않는다. 정리 결과가 한 글자라도 달라지면 content_hash 가 전부 바뀌므로
# JS 정의를 그대로 적는다.
JS_SPACE = "\t\n\v\f\r    -     　﻿"
_WHITESPACE_RUN = re.compile(f"[{JS_SPACE}]+")
_JS_SPACE_CLASS = re.compile(f"[{JS_SPACE}]")

_CDATA = re.compile(r"<!\[CDATA\[([\s\S]*?)\]\]>")
_ENTITY = re.compile(r"&(#x?[0-9a-f]+|[a-z]+);", re.IGNORECASE)
_SCRIPT = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.IGNORECASE)
_STYLE = re.compile(r"<style\b[^>]*>[\s\S]*?</style>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " "}

DEFAULT_MAX = 6000


def _entity(match: re.Match[str]) -> str:
    entity = match.group(1)
    if entity[0] == "#":
        is_hex = len(entity) > 1 and entity[1].lower() == "x"
        digits = entity[2:] if is_hex else entity[1:]
        try:
            code = int(digits, 16 if is_hex else 10)
        except ValueError:
            # JS: Number.parseInt("") -> NaN -> Number.isFinite(NaN) false -> ""
            return ""
        try:
            return chr(code)
        except (ValueError, OverflowError):
            # JS String.fromCodePoint 는 범위를 벗어나면 던진다. 원본은 그 경우를
            # 다루지 않으므로 여기서는 빈 문자열로 흘린다.
            return ""
    return _ENTITIES.get(entity.lower(), f"&{entity};")


def decode_xml(value: str) -> str:
    return _ENTITY.sub(_entity, _CDATA.sub(r"\1", value))


def clean_text(value: str, max_length: int = DEFAULT_MAX) -> str:
    """
    태그를 지우고 공백을 한 칸으로 접은 뒤 자른다.

    자르기는 코드포인트 단위다. JS 는 UTF-16 코드유닛으로 자르므로 BMP 밖 문자(이모지)가
    있으면 경계가 한 칸 어긋날 수 있다. 한국어 본문에서는 동일하다.
    """
    text = decode_xml(value)
    text = _SCRIPT.sub(" ", text)
    text = _STYLE.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = _WHITESPACE_RUN.sub(" ", text)
    # JS 의 trim() 은 JS `\s` 집합을 벗긴다. Python 의 strip() 기본값과 다르므로 명시한다.
    text = _js_trim(text)
    return text[:max_length]


def _js_trim(value: str) -> str:
    start, end = 0, len(value)
    while start < end and _JS_SPACE_CLASS.fullmatch(value[start]):
        start += 1
    while end > start and _JS_SPACE_CLASS.fullmatch(value[end - 1]):
        end -= 1
    return value[start:end]


def tag(block: str, names: list[str]) -> str:
    """첫 번째로 내용이 있는 태그의 내부를 돌려준다. 원본과 같은 순차 탐색."""
    for name in names:
        match = re.search(
            rf"<{re.escape(name)}(?:\s[^>]*)?>([\s\S]*?)</{re.escape(name)}>",
            block,
            re.IGNORECASE,
        )
        if match and match.group(1):
            return match.group(1)
    return ""

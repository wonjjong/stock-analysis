"""
robots.txt 판정. `app/lib/news-crawler.ts` 의 robotsAllows 이식.

## urllib.robotparser 를 쓰지 않는 이유

원본은 표준 파서가 재현하지 않는 네 가지 동작을 갖는다.

1. **양방향 agent prefix 매치** — `"signalistresearchbot".startsWith(agent)` 와
   `agent.startsWith("signalistresearchbot")` 를 둘 다 본다.
2. **최장 패턴 승리, 동률이면 allow** — RobotFileParser 의 우선순위와 다르다.
3. **빈 줄에서 그룹 리셋** (`hasDirectives` 상태 기계)
4. **값이 빈 `Disallow:` 는 규칙이 아니다** (전체 허용을 뜻하는 관례)

30줄이므로 그대로 이식한다. 라이브러리로 치환하면 판정이 달라져 수집 대상이 바뀐다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

AGENT = "signalistresearchbot"

# JS 가 이스케이프하는 문자 집합. Python re.escape 는 더 많이 이스케이프하므로 그대로
# 쓰면 패턴 의미가 달라진다.
_JS_ESCAPE = re.compile(r"[.+?^${}()|\[\]\\]")
_COMMENT = re.compile(r"\s*#.*$")


@dataclass(frozen=True, slots=True)
class RobotsRule:
    allow: bool
    pattern: str


def _to_regex(pattern: str) -> re.Pattern[str] | None:
    escaped = _JS_ESCAPE.sub(lambda m: "\\" + m.group(0), pattern)
    escaped = escaped.replace("*", ".*")
    # 원본은 끝의 `\$` 를 앵커 `$` 로 되돌린다(robots 의 `$` 는 경로 끝을 뜻한다).
    escaped = re.sub(r"\\\$$", "$", escaped)
    try:
        return re.compile(f"^{escaped}")
    except re.error:
        return None


def robots_allows(text: str, target_url: str) -> bool:
    exact: list[RobotsRule] = []
    fallback: list[RobotsRule] = []
    agents: list[str] = []
    has_directives = False

    for raw_line in re.split(r"\r?\n", text):
        line = _COMMENT.sub("", raw_line).strip()
        if not line:
            agents = []
            has_directives = False
            continue
        separator = line.find(":")
        if separator < 0:
            continue
        key = line[:separator].strip().lower()
        value = line[separator + 1 :].strip()

        if key == "user-agent":
            if has_directives:
                agents = []
            agents.append(value.lower())
            has_directives = False
            continue
        if key not in ("allow", "disallow"):
            continue
        has_directives = True
        if not value:
            continue

        rule = RobotsRule(allow=key == "allow", pattern=value)
        if any(AGENT.startswith(agent) or agent.startswith(AGENT) for agent in agents):
            exact.append(rule)
        elif "*" in agents:
            fallback.append(rule)

    rules = exact or fallback
    parts = urlsplit(target_url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")

    matched: list[RobotsRule] = []
    for rule in rules:
        compiled = _to_regex(rule.pattern)
        if compiled is not None:
            if compiled.search(path):
                matched.append(rule)
        elif path.startswith(rule.pattern):
            matched.append(rule)

    # 최장 패턴 우선, 길이가 같으면 allow 우선.
    matched.sort(key=lambda rule: (len(rule.pattern), rule.allow), reverse=True)
    return matched[0].allow if matched else True

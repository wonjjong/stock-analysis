"""
OpenAI 호환 Chat Completions 어댑터. `app/lib/llm.ts` 의 순수 부분 이식.

base URL 과 모델명만 바꾸면 OpenAI · Gemini(호환 엔드포인트) · DeepSeek · Qwen · Groq ·
OpenRouter 를 같은 코드로 부른다. DB 를 만지는 페일오버는 `news/services/llm.py` 에 있다.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

DEFAULT_TIMEOUT_MS = 25_000
MIN_TIMEOUT_MS = 5_000
MAX_TIMEOUT_MS = 60_000
KST_OFFSET = timedelta(hours=9)
# 503·네트워크 오류는 Gemini 같은 외부 공급자의 순간 혼잡일 수 있다. 한 번의 실패로
# 공급자를 쿨다운시키기 전에 같은 요청을 짧게 다시 보낸다.
TRANSIENT_RETRY_DELAYS_SECONDS = (1.0, 2.0)

_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_QUOTA_HINT = re.compile(r"quota|exhaust|limit|billing|credit", re.IGNORECASE)


class FailureKind:
    """문자열 상수로 둔다 — DB 의 `last_status` 에 그대로 저장되고 화면에 노출된다."""

    QUOTA = "한도 초과"
    AUTH = "인증 오류"
    TRANSIENT = "일시 오류"
    REQUEST = "요청 오류"
    SUCCESS = "성공"


@dataclass(frozen=True, slots=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    timeout_ms: int


class LlmError(RuntimeError):
    def __init__(self, message: str, kind: str, status: int = 0) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


def timeout_ms() -> int:
    raw = os.environ.get("SIGNALIST_LLM_TIMEOUT_MS")
    try:
        value = int(raw) if raw else 0
    except ValueError:
        value = 0
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, value or DEFAULT_TIMEOUT_MS))


def env_config() -> LlmConfig | None:
    """DB 에 공급자가 하나도 없을 때만 쓰는 환경변수 폴백."""
    api_key = os.environ.get("SIGNALIST_LLM_API_KEY") or os.environ.get(
        "SIGNALIST_OPENAI_API_KEY"
    )
    if not api_key:
        return None
    base_url = (
        os.environ.get("SIGNALIST_LLM_BASE_URL") or "https://api.openai.com/v1"
    ).rstrip("/")
    model = (
        os.environ.get("SIGNALIST_LLM_MODEL")
        or os.environ.get("SIGNALIST_OPENAI_NEWS_MODEL")
        or "gpt-5.6-terra"
    )
    return LlmConfig(base_url, api_key, model, timeout_ms())


def extract_json(text: str) -> object:
    """
    코드펜스로 감싸 오거나 설명을 덧붙이는 모델이 많다. 펜스를 먼저 벗기고, 그 안에서
    첫 `{` 와 마지막 `}` 사이를 잘라 파싱한다.
    """
    fenced = _FENCED.search(text)
    body = (fenced.group(1) if fenced else text).strip()
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end <= start:
        raise LlmError("모델이 JSON을 반환하지 않았습니다.", FailureKind.REQUEST)
    return json.loads(body[start : end + 1])


def classify_failure(status: int, detail: str) -> str:
    """
    한도 초과와 인증 오류는 같은 키로 다시 시도해도 소용이 없어 길게 쉬게 하고, 일시
    오류만 짧게 쉬었다가 다시 쓴다.
    """
    if status == 429:
        return FailureKind.QUOTA
    if status in (401, 403):
        return FailureKind.AUTH
    if status == 402:
        return FailureKind.QUOTA
    if status >= 500 or status in (408, 0):
        return FailureKind.TRANSIENT
    if status == 400 and _QUOTA_HINT.search(detail):
        return FailureKind.QUOTA
    return FailureKind.REQUEST


def cooldown_until(kind: str, now: datetime) -> datetime:
    """
    실패 종류별로 얼마나 쉬게 할지.

    한도 초과가 분당 제한인지 일일 제한인지는 응답만 보고 알 수 없다. 한 시간 쉬되
    한국시간 자정을 넘기지 않는다 — 자정이면 어차피 무료 티어 사용량이 초기화된다.
    """
    if kind == FailureKind.QUOTA:
        kst = now + KST_OFFSET
        next_kst_midnight = datetime(
            kst.year, kst.month, kst.day, tzinfo=UTC
        ) + timedelta(days=1)
        midnight = next_kst_midnight - KST_OFFSET
        return min(midnight, now + timedelta(hours=1))
    if kind == FailureKind.AUTH:
        return now + timedelta(hours=6)
    if kind == FailureKind.REQUEST:
        return now + timedelta(minutes=30)
    return now + timedelta(minutes=5)


def llm_json(client: httpx.Client, config: LlmConfig, system: str, user: str) -> object:
    """한 공급자에게 JSON 응답을 요구한다.

    408·5xx·네트워크 오류는 같은 공급자에 짧은 지수 백오프 재시도를 한 뒤에만 호출자에게
    전달한다. 인증·형식 오류는 재시도해도 해결되지 않으므로 즉시 전달한다.
    """
    for delay in (*TRANSIENT_RETRY_DELAYS_SECONDS, None):
        try:
            response = client.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=config.timeout_ms / 1000,
            )
            if response.status_code >= 400:
                detail = response.text[:300]
                raise LlmError(
                    f"{response.status_code} {detail}",
                    classify_failure(response.status_code, detail),
                    response.status_code,
                )

            try:
                payload = response.json()
            except ValueError as reason:
                raise LlmError(
                    "응답이 JSON 이 아닙니다.", FailureKind.REQUEST, response.status_code
                ) from reason

            choices = payload.get("choices") or []
            content = (choices[0].get("message") or {}).get("content") if choices else None
            if not content:
                raise LlmError(
                    "응답에 본문이 없습니다.", FailureKind.REQUEST, response.status_code
                )

            try:
                return extract_json(content)
            except LlmError:
                raise
            except ValueError as reason:
                raise LlmError(
                    f"JSON 해석 실패: {reason}", FailureKind.REQUEST, response.status_code
                ) from reason
        except httpx.TimeoutException as reason:
            seconds = round(config.timeout_ms / 1000)
            failure = LlmError(
                f"응답이 {seconds}초를 넘겨 끊었습니다.", FailureKind.TRANSIENT
            )
            failure.__cause__ = reason
        except httpx.HTTPError as reason:
            failure = LlmError(str(reason) or "네트워크 오류", FailureKind.TRANSIENT)
            failure.__cause__ = reason
        except LlmError as reason:
            failure = reason

        if failure.kind != FailureKind.TRANSIENT or delay is None:
            raise failure
        time.sleep(delay)

    raise AssertionError("재시도 루프를 빠져나왔습니다.")

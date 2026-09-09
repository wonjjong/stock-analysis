"""
무료 티어로 시작할 수 있는 OpenAI 호환 공급자 프리셋. `app/lib/llm-presets.ts` 이식.

모델명과 무료 한도는 공급자가 수시로 바꾸므로 등록 후 화면에서 수정할 수 있게 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmPreset:
    key: str
    name: str
    base_url: str
    model: str
    priority: int
    daily_limit: int
    key_url: str
    note: str


LLM_PRESETS: tuple[LlmPreset, ...] = (
    LlmPreset(
        "gemini", "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.5-flash-lite", 10, 200,
        "https://aistudio.google.com/apikey",
        "카드 등록 없이 키를 받을 수 있는 고처리량 무료 모델입니다."
        " 무료 티어는 보낸 내용이 모델 개선에 쓰일 수 있습니다.",
    ),
    LlmPreset(
        "groq", "Groq", "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile", 20, 1000,
        "https://console.groq.com/keys",
        "무료 한도가 넉넉하고 응답이 빠릅니다. 한국어는 Gemini보다 거칠 수 있어"
        " 2순위로 두기 좋습니다.",
    ),
    LlmPreset(
        "openrouter", "OpenRouter (무료 모델)", "https://openrouter.ai/api/v1",
        "deepseek/deepseek-chat-v3-0324:free", 30, 50,
        "https://openrouter.ai/keys",
        "DeepSeek·Qwen 오픈 모델을 :free 라우트로 씁니다. 한도가 빡빡하고 모델"
        " 가용성이 자주 바뀝니다.",
    ),
    LlmPreset(
        "cerebras", "Cerebras", "https://api.cerebras.ai/v1",
        "llama-3.3-70b", 40, 500,
        "https://cloud.cerebras.ai",
        "무료 개발자 티어가 있고 속도가 빠릅니다. 마지막 예비 공급자로 두기 좋습니다.",
    ),
)

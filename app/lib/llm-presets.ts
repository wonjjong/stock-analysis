/**
 * 무료 티어로 시작할 수 있는 OpenAI 호환 공급자 프리셋.
 * 모델명과 무료 한도는 공급자가 수시로 바꾸므로 등록 후 화면에서 수정할 수 있게 둔다.
 */
export type LlmPreset = {
  key: string; name: string; baseUrl: string; model: string; priority: number; dailyLimit: number;
  keyUrl: string; note: string;
};

export const llmPresets: LlmPreset[] = [
  {
    key: "gemini", name: "Google Gemini", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.5-flash", priority: 10, dailyLimit: 200,
    keyUrl: "https://aistudio.google.com/apikey",
    note: "카드 등록 없이 키를 받을 수 있고 한국어 요약 품질이 가장 낫습니다. 무료 티어는 보낸 내용이 모델 개선에 쓰일 수 있습니다.",
  },
  {
    key: "groq", name: "Groq", baseUrl: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile", priority: 20, dailyLimit: 1000,
    keyUrl: "https://console.groq.com/keys",
    note: "무료 한도가 넉넉하고 응답이 빠릅니다. 한국어는 Gemini보다 거칠 수 있어 2순위로 두기 좋습니다.",
  },
  {
    key: "openrouter", name: "OpenRouter (무료 모델)", baseUrl: "https://openrouter.ai/api/v1",
    model: "deepseek/deepseek-chat-v3-0324:free", priority: 30, dailyLimit: 50,
    keyUrl: "https://openrouter.ai/keys",
    note: "DeepSeek·Qwen 오픈 모델을 :free 라우트로 씁니다. 한도가 빡빡하고 모델 가용성이 자주 바뀝니다.",
  },
  {
    key: "cerebras", name: "Cerebras", baseUrl: "https://api.cerebras.ai/v1",
    model: "llama-3.3-70b", priority: 40, dailyLimit: 500,
    keyUrl: "https://cloud.cerebras.ai",
    note: "무료 개발자 티어가 있고 속도가 빠릅니다. 마지막 예비 공급자로 두기 좋습니다.",
  },
];

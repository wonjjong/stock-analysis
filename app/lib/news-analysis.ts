export type NewsAnalysis = {
  symbol: string;
  sentiment: "긍정" | "부정" | "중립";
  sentimentScore: number;
  relevance: number;
  materiality: "높음" | "보통" | "낮음";
  eventType: string;
  impactHorizon: "당일" | "단기(1~4주)" | "중기(1~2분기)" | "장기(1년+)";
  confidence: number;
  scoreAdjustment: number;
  summary: string;
  keyEvidence: string[];
  bullCase: string;
  bearCase: string;
  watchItems: string[];
  engine: "AI" | "규칙 기반 데모";
};

const positive = ["증가", "성장", "확대", "상향", "수주", "흑자", "개선", "회복", "호조", "승인", "돌파", "협력", "투자"];
const negative = ["감소", "하락", "축소", "하향", "적자", "부진", "지연", "규제", "소송", "리콜", "중단", "해킹", "우려"];
const material = ["실적", "매출", "영업이익", "순이익", "가이던스", "수주", "계약", "인수", "합병", "유상증자", "배당", "자사주", "규제", "소송"];

function count(text: string, words: string[]) { return words.reduce((sum, word) => sum + (text.includes(word) ? 1 : 0), 0); }
function clamp(value: number, min = 0, max = 100) { return Math.max(min, Math.min(max, value)); }

export function analyzeNewsLocally(text: string, symbol: string, company: string): NewsAnalysis {
  const compact = text.replace(/\s+/g, " ").trim();
  const pos = count(compact, positive); const neg = count(compact, negative); const important = count(compact, material);
  const raw = pos - neg;
  const sentimentScore = clamp(50 + raw * 11);
  const sentiment = raw > 0 ? "긍정" : raw < 0 ? "부정" : "중립";
  const explicit = compact.toLowerCase().includes(symbol.toLowerCase()) || compact.includes(company);
  const relevance = clamp((explicit ? 76 : 48) + Math.min(important * 5, 19));
  const materiality = important >= 3 ? "높음" : important >= 1 ? "보통" : "낮음";
  const eventType = compact.includes("실적") || compact.includes("매출") ? "실적·가이던스" : compact.includes("수주") || compact.includes("계약") ? "수주·사업계약" : compact.includes("규제") || compact.includes("소송") ? "규제·법률" : compact.includes("투자") || compact.includes("협력") ? "투자·파트너십" : "산업·시장동향";
  const impactHorizon = eventType === "실적·가이던스" ? "중기(1~2분기)" : eventType === "수주·사업계약" ? "장기(1년+)" : materiality === "낮음" ? "당일" : "단기(1~4주)";
  const scoreAdjustment = Math.round(clamp(raw * (materiality === "높음" ? 2.4 : materiality === "보통" ? 1.5 : .7), -8, 8));
  const sentences = compact.split(/(?<=[.!?。]|다\.)\s+/).filter((item) => item.length > 18);
  const keyEvidence = (sentences.length ? sentences : [compact]).slice(0, 3).map((item) => item.slice(0, 150));
  return {
    symbol, sentiment, sentimentScore, relevance, materiality, eventType, impactHorizon,
    confidence: clamp(52 + (explicit ? 15 : 0) + Math.min(compact.length / 45, 18) + important * 2),
    scoreAdjustment,
    summary: `${company} 관련 ${eventType} 뉴스입니다. ${sentiment === "긍정" ? "이익 기대 또는 사업 가시성에 우호적" : sentiment === "부정" ? "실적 또는 밸류에이션의 하방 위험을 높일 수 있는" : "방향성이 확정되지 않은"} 신호로 분류했습니다.`,
    keyEvidence,
    bullCase: pos > 0 ? "보도 내용이 실제 매출·이익 추정치 상향으로 연결되면 주가 재평가의 근거가 됩니다." : "추가 공시에서 정량적 성과가 확인되면 중립 판단이 개선될 수 있습니다.",
    bearCase: neg > 0 ? "부정 요인이 장기화되거나 비용으로 현실화되면 현재 기대치를 낮춰야 합니다." : "기사에 계약 금액·이익 기여 시점이 없으면 기대감만 선반영됐을 가능성이 있습니다.",
    watchItems: ["회사 공시 또는 공식 발표로 사실 확인", "다음 실적 추정치 변화", "동일 사건의 후속 보도와 가격·거래량 반응"],
    engine: "규칙 기반 데모",
  };
}

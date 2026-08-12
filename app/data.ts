export type Market = "KR" | "US";

export type Stock = {
  symbol: string;
  name: string;
  market: Market;
  exchange: string;
  sector: string;
  currency: "KRW" | "USD";
  price: number;
  change: number;
  score: number;
  confidence: number;
  action: "매수 유효" | "관찰" | "위험 주의";
  thesis: string;
  risk: string;
  per: number;
  pbr: number;
  roe: number;
  target: number;
  stop: number;
  factors: { label: string; value: number }[];
};

export const stocks: Stock[] = [
  {
    symbol: "005930", name: "삼성전자", market: "KR", exchange: "KOSPI", sector: "반도체", currency: "KRW",
    price: 87400, change: 2.34, score: 88, confidence: 82, action: "매수 유효",
    thesis: "메모리 가격 반등과 고대역폭 메모리 믹스 개선이 실적 눈높이를 끌어올리고 있습니다.",
    risk: "원화 강세와 파운드리 수율 회복 지연", per: 18.4, pbr: 1.62, roe: 9.8, target: 96000, stop: 82100,
    factors: [{ label: "실적", value: 91 }, { label: "가치", value: 72 }, { label: "추세", value: 86 }, { label: "뉴스", value: 88 }],
  },
  {
    symbol: "000660", name: "SK하이닉스", market: "KR", exchange: "KOSPI", sector: "반도체", currency: "KRW",
    price: 286500, change: 4.12, score: 85, confidence: 79, action: "매수 유효",
    thesis: "HBM 공급 우위와 서버 DRAM 수요가 단기 이익 모멘텀을 지지합니다.",
    risk: "높아진 밸류에이션과 AI 투자 사이클 둔화", per: 11.8, pbr: 2.71, roe: 25.4, target: 312000, stop: 269000,
    factors: [{ label: "실적", value: 94 }, { label: "가치", value: 67 }, { label: "추세", value: 90 }, { label: "뉴스", value: 82 }],
  },
  {
    symbol: "105560", name: "KB금융", market: "KR", exchange: "KOSPI", sector: "은행", currency: "KRW",
    price: 118900, change: 1.45, score: 81, confidence: 76, action: "관찰",
    thesis: "주주환원 확대와 안정적인 순이자마진이 하방을 지지합니다.",
    risk: "대손비용 상승과 금리 하락 속도", per: 7.9, pbr: 0.72, roe: 10.6, target: 128000, stop: 112000,
    factors: [{ label: "실적", value: 78 }, { label: "가치", value: 92 }, { label: "추세", value: 71 }, { label: "뉴스", value: 74 }],
  },
  {
    symbol: "012450", name: "한화에어로스페이스", market: "KR", exchange: "KOSPI", sector: "방산", currency: "KRW",
    price: 946000, change: -1.08, score: 78, confidence: 72, action: "관찰",
    thesis: "수주잔고는 견고하지만 최근 상승폭을 고려하면 눌림 확인이 필요합니다.",
    risk: "차익실현과 수출계약 일정 변동", per: 28.6, pbr: 5.14, roe: 19.2, target: 1010000, stop: 892000,
    factors: [{ label: "실적", value: 85 }, { label: "가치", value: 48 }, { label: "추세", value: 82 }, { label: "뉴스", value: 86 }],
  },
  {
    symbol: "035420", name: "NAVER", market: "KR", exchange: "KOSPI", sector: "인터넷", currency: "KRW",
    price: 271000, change: 0.74, score: 75, confidence: 69, action: "관찰",
    thesis: "커머스 수익성 개선과 AI 검색 전환 기대가 밸류에이션 부담을 완화합니다.",
    risk: "AI 투자비 증가와 광고 경기 둔화", per: 20.2, pbr: 1.58, roe: 8.5, target: 292000, stop: 254000,
    factors: [{ label: "실적", value: 73 }, { label: "가치", value: 69 }, { label: "추세", value: 70 }, { label: "뉴스", value: 81 }],
  },
  {
    symbol: "NVDA", name: "NVIDIA", market: "US", exchange: "NASDAQ", sector: "Semiconductors", currency: "USD",
    price: 184.62, change: 2.91, score: 90, confidence: 84, action: "매수 유효",
    thesis: "AI 가속기 수요와 소프트웨어 생태계가 실적 추정치 상향을 견인합니다.",
    risk: "고객 집중도와 수출 규제", per: 37.5, pbr: 28.4, roe: 91.7, target: 202, stop: 174,
    factors: [{ label: "실적", value: 96 }, { label: "가치", value: 51 }, { label: "추세", value: 92 }, { label: "뉴스", value: 90 }],
  },
  {
    symbol: "MSFT", name: "Microsoft", market: "US", exchange: "NASDAQ", sector: "Software", currency: "USD",
    price: 521.33, change: 1.26, score: 86, confidence: 82, action: "매수 유효",
    thesis: "Azure 성장과 Copilot 확산이 반복 매출의 질을 높이고 있습니다.",
    risk: "대규모 AI 설비투자와 규제", per: 34.1, pbr: 11.9, roe: 38.2, target: 558, stop: 493,
    factors: [{ label: "실적", value: 91 }, { label: "가치", value: 58 }, { label: "추세", value: 84 }, { label: "뉴스", value: 86 }],
  },
  {
    symbol: "GOOGL", name: "Alphabet", market: "US", exchange: "NASDAQ", sector: "Interactive Media", currency: "USD",
    price: 214.08, change: 0.88, score: 82, confidence: 78, action: "매수 유효",
    thesis: "검색 수익성, 클라우드 성장과 상대적으로 낮은 멀티플이 조화를 이룹니다.",
    risk: "AI 검색 전환 비용과 반독점 소송", per: 25.7, pbr: 8.2, roe: 32.1, target: 232, stop: 201,
    factors: [{ label: "실적", value: 86 }, { label: "가치", value: 76 }, { label: "추세", value: 78 }, { label: "뉴스", value: 80 }],
  },
  {
    symbol: "JPM", name: "JPMorgan Chase", market: "US", exchange: "NYSE", sector: "Banks", currency: "USD",
    price: 309.42, change: -0.42, score: 77, confidence: 73, action: "관찰",
    thesis: "높은 자본비율과 수수료 수익이 금리 정상화 구간의 방어력을 제공합니다.",
    risk: "신용비용 증가와 장단기 금리차 축소", per: 14.2, pbr: 2.31, roe: 17.8, target: 326, stop: 294,
    factors: [{ label: "실적", value: 82 }, { label: "가치", value: 74 }, { label: "추세", value: 69 }, { label: "뉴스", value: 71 }],
  },
  {
    symbol: "AMZN", name: "Amazon", market: "US", exchange: "NASDAQ", sector: "Retail", currency: "USD",
    price: 238.76, change: 1.67, score: 75, confidence: 70, action: "관찰",
    thesis: "AWS와 광고의 마진 개선이 소비 경기 변동을 상쇄하고 있습니다.",
    risk: "소비 둔화와 물류비 재상승", per: 31.8, pbr: 7.4, roe: 24.6, target: 256, stop: 224,
    factors: [{ label: "실적", value: 84 }, { label: "가치", value: 56 }, { label: "추세", value: 76 }, { label: "뉴스", value: 74 }],
  },
];

export const macro = [
  { label: "VIX", value: "16.17", change: "-5.38%", tone: "positive", note: "미국 변동성" },
  { label: "V-KOSPI", value: "22.84", change: "+0.62", tone: "negative", note: "한국 변동성" },
  { label: "USD/KRW", value: "1,409.94", change: "-0.94%", tone: "positive", note: "원화 강세" },
  { label: "미 국채 10Y", value: "4.72%", change: "+7bp", tone: "negative", note: "장기금리" },
  { label: "한국 국고 3Y", value: "3.18%", change: "+2bp", tone: "neutral", note: "할인율" },
];

export const portfolio = [
  { symbol: "005930", name: "삼성전자", qty: 35, avg: 79100, price: 87400, currency: "KRW" },
  { symbol: "000660", name: "SK하이닉스", qty: 8, avg: 244500, price: 286500, currency: "KRW" },
  { symbol: "MSFT", name: "Microsoft", qty: 4, avg: 468.2, price: 521.33, currency: "USD" },
];

export const news = [
  { source: "전자공시", time: "42분 전", title: "반도체 수출 회복세 지속…고부가 메모리 비중 확대", sentiment: "긍정", materiality: "높음" },
  { source: "Reuters", time: "2시간 전", title: "AI infrastructure spending remains resilient into next quarter", sentiment: "긍정", materiality: "높음" },
  { source: "한국경제", time: "3시간 전", title: "원·달러 환율 하락, 외국인 대형주 수급에 우호적", sentiment: "중립", materiality: "보통" },
];

export function formatPrice(stock: Stock, value = stock.price) {
  return stock.currency === "KRW"
    ? `${Math.round(value).toLocaleString("ko-KR")}원`
    : `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function getStock(symbol: string) {
  return stocks.find((stock) => stock.symbol.toLowerCase() === symbol.toLowerCase()) ?? stocks[0];
}

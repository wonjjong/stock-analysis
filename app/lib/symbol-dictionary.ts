/**
 * 뉴스 본문에서 종목을 찾아내기 위한 사전.
 * 그룹명(삼성, 현대, LG)처럼 여러 상장사를 가리키는 말은 오탐이 많아 별칭에 넣지 않습니다.
 */
export type SymbolEntry = { symbol: string; name: string; market: "KR" | "US"; sector: string; aliases: string[] };

export const symbolDictionary: SymbolEntry[] = [
  { symbol: "005930", name: "삼성전자", market: "KR", sector: "반도체", aliases: ["삼성전자", "삼성전자우"] },
  { symbol: "000660", name: "SK하이닉스", market: "KR", sector: "반도체", aliases: ["SK하이닉스", "하이닉스"] },
  { symbol: "373220", name: "LG에너지솔루션", market: "KR", sector: "2차전지", aliases: ["LG에너지솔루션", "엘지에너지솔루션", "LG엔솔"] },
  { symbol: "207940", name: "삼성바이오로직스", market: "KR", sector: "바이오", aliases: ["삼성바이오로직스", "삼바"] },
  { symbol: "005380", name: "현대차", market: "KR", sector: "자동차", aliases: ["현대차", "현대자동차"] },
  { symbol: "000270", name: "기아", market: "KR", sector: "자동차", aliases: ["기아자동차", "기아차"] },
  { symbol: "005490", name: "POSCO홀딩스", market: "KR", sector: "철강", aliases: ["POSCO홀딩스", "포스코홀딩스", "포스코"] },
  { symbol: "051910", name: "LG화학", market: "KR", sector: "화학", aliases: ["LG화학", "엘지화학"] },
  { symbol: "006400", name: "삼성SDI", market: "KR", sector: "2차전지", aliases: ["삼성SDI"] },
  { symbol: "035420", name: "NAVER", market: "KR", sector: "인터넷", aliases: ["네이버", "NAVER"] },
  { symbol: "035720", name: "카카오", market: "KR", sector: "인터넷", aliases: ["카카오"] },
  { symbol: "323410", name: "카카오뱅크", market: "KR", sector: "은행", aliases: ["카카오뱅크"] },
  { symbol: "377300", name: "카카오페이", market: "KR", sector: "핀테크", aliases: ["카카오페이"] },
  { symbol: "105560", name: "KB금융", market: "KR", sector: "은행", aliases: ["KB금융", "국민은행", "KB국민은행"] },
  { symbol: "055550", name: "신한지주", market: "KR", sector: "은행", aliases: ["신한지주", "신한금융", "신한은행"] },
  { symbol: "086790", name: "하나금융지주", market: "KR", sector: "은행", aliases: ["하나금융지주", "하나금융", "하나은행"] },
  { symbol: "316140", name: "우리금융지주", market: "KR", sector: "은행", aliases: ["우리금융지주", "우리금융", "우리은행"] },
  { symbol: "138040", name: "메리츠금융지주", market: "KR", sector: "증권", aliases: ["메리츠금융지주", "메리츠금융"] },
  { symbol: "012450", name: "한화에어로스페이스", market: "KR", sector: "방산", aliases: ["한화에어로스페이스", "한화에어로"] },
  { symbol: "047810", name: "한국항공우주", market: "KR", sector: "방산", aliases: ["한국항공우주", "KAI"] },
  { symbol: "064350", name: "현대로템", market: "KR", sector: "방산", aliases: ["현대로템"] },
  { symbol: "042660", name: "한화오션", market: "KR", sector: "조선", aliases: ["한화오션", "대우조선해양"] },
  { symbol: "329180", name: "HD현대중공업", market: "KR", sector: "조선", aliases: ["HD현대중공업", "현대중공업"] },
  { symbol: "010140", name: "삼성중공업", market: "KR", sector: "조선", aliases: ["삼성중공업"] },
  { symbol: "009540", name: "HD한국조선해양", market: "KR", sector: "조선", aliases: ["HD한국조선해양", "한국조선해양"] },
  { symbol: "015760", name: "한국전력", market: "KR", sector: "유틸리티", aliases: ["한국전력", "한전"] },
  { symbol: "034020", name: "두산에너빌리티", market: "KR", sector: "발전설비", aliases: ["두산에너빌리티", "두산중공업"] },
  { symbol: "241560", name: "두산밥캣", market: "KR", sector: "기계", aliases: ["두산밥캣"] },
  { symbol: "000880", name: "한화", market: "KR", sector: "지주", aliases: ["한화솔루션", "한화시스템"] },
  { symbol: "010130", name: "고려아연", market: "KR", sector: "비철금속", aliases: ["고려아연"] },
  { symbol: "011200", name: "HMM", market: "KR", sector: "해운", aliases: ["HMM"] },
  { symbol: "003490", name: "대한항공", market: "KR", sector: "항공", aliases: ["대한항공"] },
  { symbol: "032640", name: "LG유플러스", market: "KR", sector: "통신", aliases: ["LG유플러스", "엘지유플러스"] },
  { symbol: "017670", name: "SK텔레콤", market: "KR", sector: "통신", aliases: ["SK텔레콤", "SKT"] },
  { symbol: "030200", name: "KT", market: "KR", sector: "통신", aliases: ["KT주식회사"] },
  { symbol: "066570", name: "LG전자", market: "KR", sector: "가전", aliases: ["LG전자", "엘지전자"] },
  { symbol: "009150", name: "삼성전기", market: "KR", sector: "전자부품", aliases: ["삼성전기"] },
  { symbol: "011070", name: "LG이노텍", market: "KR", sector: "전자부품", aliases: ["LG이노텍"] },
  { symbol: "034730", name: "SK", market: "KR", sector: "지주", aliases: ["SK이노베이션", "SK온"] },
  { symbol: "096770", name: "SK이노베이션", market: "KR", sector: "정유", aliases: ["SK이노베이션"] },
  { symbol: "010950", name: "S-Oil", market: "KR", sector: "정유", aliases: ["에쓰오일", "S-Oil", "에스오일"] },
  { symbol: "051900", name: "LG생활건강", market: "KR", sector: "소비재", aliases: ["LG생활건강"] },
  { symbol: "090430", name: "아모레퍼시픽", market: "KR", sector: "화장품", aliases: ["아모레퍼시픽", "아모레"] },
  { symbol: "097950", name: "CJ제일제당", market: "KR", sector: "음식료", aliases: ["CJ제일제당"] },
  { symbol: "271560", name: "오리온", market: "KR", sector: "음식료", aliases: ["오리온"] },
  { symbol: "282330", name: "BGF리테일", market: "KR", sector: "유통", aliases: ["BGF리테일", "CU편의점"] },
  { symbol: "069960", name: "현대백화점", market: "KR", sector: "유통", aliases: ["현대백화점"] },
  { symbol: "004170", name: "신세계", market: "KR", sector: "유통", aliases: ["신세계백화점"] },
  { symbol: "139480", name: "이마트", market: "KR", sector: "유통", aliases: ["이마트"] },
  { symbol: "068270", name: "셀트리온", market: "KR", sector: "바이오", aliases: ["셀트리온"] },
  { symbol: "128940", name: "한미약품", market: "KR", sector: "제약", aliases: ["한미약품"] },
  { symbol: "000100", name: "유한양행", market: "KR", sector: "제약", aliases: ["유한양행"] },
  { symbol: "326030", name: "SK바이오팜", market: "KR", sector: "바이오", aliases: ["SK바이오팜"] },
  { symbol: "196170", name: "알테오젠", market: "KR", sector: "바이오", aliases: ["알테오젠"] },
  { symbol: "247540", name: "에코프로비엠", market: "KR", sector: "2차전지", aliases: ["에코프로비엠"] },
  { symbol: "086520", name: "에코프로", market: "KR", sector: "2차전지", aliases: ["에코프로"] },
  { symbol: "066970", name: "엘앤에프", market: "KR", sector: "2차전지", aliases: ["엘앤에프"] },
  { symbol: "003670", name: "포스코퓨처엠", market: "KR", sector: "2차전지", aliases: ["포스코퓨처엠"] },
  { symbol: "042700", name: "한미반도체", market: "KR", sector: "반도체장비", aliases: ["한미반도체"] },
  { symbol: "000990", name: "DB하이텍", market: "KR", sector: "반도체", aliases: ["DB하이텍"] },
  { symbol: "403870", name: "HPSP", market: "KR", sector: "반도체장비", aliases: ["HPSP"] },
  { symbol: "058470", name: "리노공업", market: "KR", sector: "반도체장비", aliases: ["리노공업"] },
  { symbol: "112040", name: "위메이드", market: "KR", sector: "게임", aliases: ["위메이드"] },
  { symbol: "036570", name: "엔씨소프트", market: "KR", sector: "게임", aliases: ["엔씨소프트", "NC소프트"] },
  { symbol: "251270", name: "넷마블", market: "KR", sector: "게임", aliases: ["넷마블"] },
  { symbol: "259960", name: "크래프톤", market: "KR", sector: "게임", aliases: ["크래프톤"] },
  { symbol: "352820", name: "하이브", market: "KR", sector: "엔터", aliases: ["하이브", "HYBE"] },
  { symbol: "041510", name: "에스엠", market: "KR", sector: "엔터", aliases: ["에스엠엔터테인먼트", "SM엔터테인먼트"] },
  { symbol: "122870", name: "와이지엔터테인먼트", market: "KR", sector: "엔터", aliases: ["와이지엔터테인먼트", "YG엔터테인먼트"] },
  { symbol: "035900", name: "JYP Ent.", market: "KR", sector: "엔터", aliases: ["JYP엔터테인먼트"] },
  { symbol: "018260", name: "삼성에스디에스", market: "KR", sector: "IT서비스", aliases: ["삼성에스디에스", "삼성SDS"] },
  { symbol: "267250", name: "HD현대", market: "KR", sector: "지주", aliases: ["HD현대"] },
  { symbol: "012330", name: "현대모비스", market: "KR", sector: "자동차부품", aliases: ["현대모비스"] },
  { symbol: "161390", name: "한국타이어앤테크놀로지", market: "KR", sector: "자동차부품", aliases: ["한국타이어"] },
  { symbol: "028260", name: "삼성물산", market: "KR", sector: "건설", aliases: ["삼성물산"] },
  { symbol: "000720", name: "현대건설", market: "KR", sector: "건설", aliases: ["현대건설"] },
  { symbol: "006360", name: "GS건설", market: "KR", sector: "건설", aliases: ["GS건설"] },
  { symbol: "047050", name: "포스코인터내셔널", market: "KR", sector: "상사", aliases: ["포스코인터내셔널"] },
  { symbol: "078930", name: "GS", market: "KR", sector: "지주", aliases: ["GS칼텍스"] },
  { symbol: "016360", name: "삼성증권", market: "KR", sector: "증권", aliases: ["삼성증권"] },
  { symbol: "005940", name: "NH투자증권", market: "KR", sector: "증권", aliases: ["NH투자증권"] },
  { symbol: "006800", name: "미래에셋증권", market: "KR", sector: "증권", aliases: ["미래에셋증권"] },
  { symbol: "071050", name: "한국금융지주", market: "KR", sector: "증권", aliases: ["한국금융지주", "한국투자증권"] },
  { symbol: "032830", name: "삼성생명", market: "KR", sector: "보험", aliases: ["삼성생명"] },
  { symbol: "000810", name: "삼성화재", market: "KR", sector: "보험", aliases: ["삼성화재"] },
  { symbol: "079550", name: "LIG넥스원", market: "KR", sector: "방산", aliases: ["LIG넥스원"] },
  { symbol: "272210", name: "한화시스템", market: "KR", sector: "방산", aliases: ["한화시스템"] },
  { symbol: "298040", name: "효성중공업", market: "KR", sector: "전력기기", aliases: ["효성중공업"] },
  { symbol: "010120", name: "LS ELECTRIC", market: "KR", sector: "전력기기", aliases: ["LS일렉트릭", "LS ELECTRIC"] },
  { symbol: "267260", name: "HD현대일렉트릭", market: "KR", sector: "전력기기", aliases: ["HD현대일렉트릭", "현대일렉트릭"] },

  { symbol: "NVDA", name: "NVIDIA", market: "US", sector: "반도체", aliases: ["엔비디아", "NVIDIA", "NVDA"] },
  { symbol: "AAPL", name: "Apple", market: "US", sector: "IT하드웨어", aliases: ["애플", "Apple", "AAPL"] },
  { symbol: "MSFT", name: "Microsoft", market: "US", sector: "소프트웨어", aliases: ["마이크로소프트", "Microsoft", "MSFT"] },
  { symbol: "GOOGL", name: "Alphabet", market: "US", sector: "인터넷", aliases: ["알파벳", "구글", "Alphabet", "GOOGL"] },
  { symbol: "AMZN", name: "Amazon", market: "US", sector: "유통", aliases: ["아마존", "Amazon", "AMZN"] },
  { symbol: "META", name: "Meta Platforms", market: "US", sector: "인터넷", aliases: ["메타플랫폼스", "Meta Platforms", "META"] },
  { symbol: "TSLA", name: "Tesla", market: "US", sector: "자동차", aliases: ["테슬라", "Tesla", "TSLA"] },
  { symbol: "AVGO", name: "Broadcom", market: "US", sector: "반도체", aliases: ["브로드컴", "Broadcom", "AVGO"] },
  { symbol: "AMD", name: "AMD", market: "US", sector: "반도체", aliases: ["AMD"] },
  { symbol: "INTC", name: "Intel", market: "US", sector: "반도체", aliases: ["인텔", "Intel", "INTC"] },
  { symbol: "MU", name: "Micron", market: "US", sector: "반도체", aliases: ["마이크론", "Micron"] },
  { symbol: "TSM", name: "TSMC", market: "US", sector: "반도체", aliases: ["TSMC", "타이완반도체"] },
  { symbol: "ASML", name: "ASML", market: "US", sector: "반도체장비", aliases: ["ASML"] },
  { symbol: "QCOM", name: "Qualcomm", market: "US", sector: "반도체", aliases: ["퀄컴", "Qualcomm", "QCOM"] },
  { symbol: "ARM", name: "Arm Holdings", market: "US", sector: "반도체", aliases: ["Arm Holdings", "ARM홀딩스"] },
  { symbol: "JPM", name: "JPMorgan Chase", market: "US", sector: "은행", aliases: ["JP모건", "JPMorgan", "JPM"] },
  { symbol: "GS", name: "Goldman Sachs", market: "US", sector: "증권", aliases: ["골드만삭스", "Goldman Sachs"] },
  { symbol: "BRK.B", name: "Berkshire Hathaway", market: "US", sector: "복합", aliases: ["버크셔해서웨이", "Berkshire"] },
  { symbol: "LLY", name: "Eli Lilly", market: "US", sector: "제약", aliases: ["일라이릴리", "Eli Lilly"] },
  { symbol: "NVO", name: "Novo Nordisk", market: "US", sector: "제약", aliases: ["노보노디스크", "Novo Nordisk"] },
  { symbol: "JNJ", name: "Johnson & Johnson", market: "US", sector: "제약", aliases: ["존슨앤드존슨", "Johnson & Johnson"] },
  { symbol: "XOM", name: "Exxon Mobil", market: "US", sector: "에너지", aliases: ["엑슨모빌", "Exxon"] },
  { symbol: "BA", name: "Boeing", market: "US", sector: "항공우주", aliases: ["보잉", "Boeing"] },
  { symbol: "NFLX", name: "Netflix", market: "US", sector: "미디어", aliases: ["넷플릭스", "Netflix", "NFLX"] },
  { symbol: "ORCL", name: "Oracle", market: "US", sector: "소프트웨어", aliases: ["오라클", "Oracle", "ORCL"] },
  { symbol: "PLTR", name: "Palantir", market: "US", sector: "소프트웨어", aliases: ["팔란티어", "Palantir", "PLTR"] },
  { symbol: "COIN", name: "Coinbase", market: "US", sector: "핀테크", aliases: ["코인베이스", "Coinbase"] },
  { symbol: "UBER", name: "Uber", market: "US", sector: "플랫폼", aliases: ["우버", "Uber"] },
  { symbol: "DIS", name: "Walt Disney", market: "US", sector: "미디어", aliases: ["디즈니", "Disney"] },
  { symbol: "WMT", name: "Walmart", market: "US", sector: "유통", aliases: ["월마트", "Walmart"] },
];

export type SymbolMatch = { symbol: string; company: string; market: "KR" | "US"; sector: string; mentions: number; relevance: number; matchType: "사전" };

const latin = /^[\x20-\x7E]+$/;

/** 공유 버튼·제보 안내 같은 상투 문구. 종목명을 세기 전에 지운다. */
const noiseTerms = ["카카오톡", "카카오스토리", "카카오채널", "네이버 블로그", "네이버블로그", "네이버 밴드", "네이버밴드", "네이버 뉴스", "네이버 메인", "구글 플레이", "애플 앱스토어", "구글플레이"];

function occurrences(haystack: string, needle: string) {
  if (!needle) return 0;
  if (latin.test(needle)) {
    const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // 영문·티커는 단어 경계를 요구해 ARM이 alarm에 걸리는 오탐을 막는다.
    return (haystack.match(new RegExp(`(?<![A-Za-z0-9])${escaped}(?![A-Za-z0-9])`, "gi")) ?? []).length;
  }
  let count = 0;
  let index = haystack.indexOf(needle);
  while (index >= 0) { count += 1; index = haystack.indexOf(needle, index + needle.length); }
  return count;
}

/**
 * 제목과 본문에서 종목을 찾는다. 긴 별칭부터 세어 이미 센 자리를 지우므로
 * '카카오뱅크' 기사가 '카카오'로도 중복 집계되지 않는다.
 */
export function matchSymbols(title: string, body: string): SymbolMatch[] {
  const entries = symbolDictionary
    .flatMap((entry) => entry.aliases.map((alias) => ({ entry, alias })))
    .sort((left, right) => right.alias.length - left.alias.length);

  let scanTitle = title;
  let scanBody = body;
  for (const noise of noiseTerms) {
    scanTitle = scanTitle.split(noise).join(" ");
    scanBody = scanBody.split(noise).join(" ");
  }
  const found = new Map<string, SymbolMatch>();
  for (const { entry, alias } of entries) {
    const inTitle = occurrences(scanTitle, alias);
    const inBody = occurrences(scanBody, alias);
    if (!inTitle && !inBody) continue;
    if (inTitle) scanTitle = scanTitle.split(alias).join(" ");
    if (inBody) scanBody = scanBody.split(alias).join(" ");
    const mentions = inTitle + inBody;
    const existing = found.get(entry.symbol);
    const relevance = Math.max(0, Math.min(100, (inTitle ? 72 : 40) + Math.min(mentions * 6, 28)));
    if (existing) {
      existing.mentions += mentions;
      existing.relevance = Math.max(existing.relevance, relevance);
      continue;
    }
    found.set(entry.symbol, { symbol: entry.symbol, company: entry.name, market: entry.market, sector: entry.sector, mentions, relevance, matchType: "사전" });
  }
  return [...found.values()].sort((left, right) => right.relevance - left.relevance || right.mentions - left.mentions).slice(0, 8);
}

export function lookupSymbol(value: string) {
  const needle = value.trim().toLowerCase();
  return symbolDictionary.find((entry) =>
    entry.symbol.toLowerCase() === needle || entry.name.toLowerCase() === needle ||
    entry.aliases.some((alias) => alias.toLowerCase() === needle)) ?? null;
}

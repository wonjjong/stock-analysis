/** 형태소 분석기 없이 조사만 떼어내 빈도 기반으로 키워드를 뽑는다. */
const particles = ["으로써", "에서는", "으로는", "이라고", "라고는", "에게서", "으로", "에서", "에는", "과는", "와는", "이나", "까지", "부터", "보다", "처럼", "만큼", "라고", "이라", "에도", "에게", "한테", "이다", "하다", "했다", "된다", "됐다", "이라는", "라는", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "과", "와", "로", "야", "요"];

const stopwords = new Set([
  "기자", "연합뉴스", "뉴스", "사진", "제공", "지난해", "올해", "내년", "지난", "이날", "관련", "대한", "위해", "통해", "따르면", "밝혔다", "말했다", "전했다",
  "대해", "가운데", "지난달", "이번", "당시", "현재", "최근", "오전", "오후", "서울", "기준", "경우", "가장", "모두", "다시", "함께", "이후", "이상", "이하",
  "그러나", "하지만", "때문", "라며", "면서", "무단", "전재", "배포", "금지", "저작권", "구독", "댓글", "그리고", "또한", "예정", "계획", "발표", "설명",
  "the", "and", "for", "with", "from", "that", "this", "has", "have", "was", "were", "will", "its", "inc", "corp", "ltd", "said", "says",
  "filed", "filer", "file", "type", "act", "size", "item", "year", "end", "state", "reuters", "bloomberg", "read", "more", "news",
]);

function stripParticle(token: string) {
  if (!/[가-힣]$/.test(token)) return token;
  for (const particle of particles) {
    if (token.length > particle.length + 1 && token.endsWith(particle)) return token.slice(0, -particle.length);
  }
  return token;
}

export function extractKeywords(title: string, body: string, limit = 8) {
  const counts = new Map<string, number>();
  const scan = (text: string, weight: number) => {
    for (const raw of text.split(/[^0-9A-Za-z가-힣%]+/)) {
      if (raw.length < 2) continue;
      const token = stripParticle(raw);
      if (token.length < 2 || token.length > 20) continue;
      if (stopwords.has(token.toLowerCase())) continue;
      if (/^\d+$/.test(token)) continue;
      // 짧은 영문 토막은 대부분 약어·조각이라 버린다.
      if (/^[A-Za-z]+$/.test(token) && token.length < 4) continue;
      counts.set(token, (counts.get(token) ?? 0) + weight);
    }
  };
  // 제목에 나온 말이 기사 주제일 확률이 높아 가중치를 크게 준다.
  scan(title, 4);
  scan(body, 1);
  return [...counts.entries()]
    .filter(([, count]) => count > 1)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([token]) => token);
}

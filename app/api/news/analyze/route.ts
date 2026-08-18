import { analyzeNewsLocally, type NewsAnalysis } from "../../../lib/news-analysis";

const schema = {
  type: "object", additionalProperties: false,
  required: ["symbol","sentiment","sentimentScore","relevance","materiality","eventType","impactHorizon","confidence","scoreAdjustment","summary","keyEvidence","bullCase","bearCase","watchItems","engine"],
  properties: {
    symbol:{type:"string"}, sentiment:{type:"string",enum:["긍정","부정","중립"]}, sentimentScore:{type:"number",minimum:0,maximum:100},
    relevance:{type:"number",minimum:0,maximum:100}, materiality:{type:"string",enum:["높음","보통","낮음"]}, eventType:{type:"string"},
    impactHorizon:{type:"string",enum:["당일","단기(1~4주)","중기(1~2분기)","장기(1년+)"]}, confidence:{type:"number",minimum:0,maximum:100},
    scoreAdjustment:{type:"number",minimum:-8,maximum:8}, summary:{type:"string"}, keyEvidence:{type:"array",items:{type:"string"},minItems:1,maxItems:3},
    bullCase:{type:"string"}, bearCase:{type:"string"}, watchItems:{type:"array",items:{type:"string"},minItems:2,maxItems:4}, engine:{type:"string",enum:["AI"]},
  },
};

function outputText(payload: Record<string, unknown>) {
  const output = payload.output as Array<{content?: Array<{type?:string;text?:string}>}> | undefined;
  return output?.flatMap((item) => item.content ?? []).find((item) => item.type === "output_text")?.text;
}

export async function POST(request: Request) {
  const body = await request.json() as { text?:string; symbol?:string; company?:string; sourceUrl?:string };
  const text = body.text?.trim() ?? ""; const symbol = body.symbol?.trim() ?? ""; const company = body.company?.trim() ?? symbol;
  if (text.length < 40 || !symbol) return Response.json({error:"종목과 40자 이상의 뉴스 본문이 필요합니다."},{status:400});
  const apiKey = process.env.SIGNALIST_OPENAI_API_KEY;
  if (!apiKey) return Response.json(analyzeNewsLocally(text,symbol,company));
  const response = await fetch("https://api.openai.com/v1/responses", {method:"POST",headers:{"Authorization":`Bearer ${apiKey}`,"Content-Type":"application/json"},body:JSON.stringify({
    model:process.env.SIGNALIST_OPENAI_NEWS_MODEL ?? "gpt-5.6-terra", store:false,
    input:[
      {role:"system",content:"당신은 기관투자자 수준의 뉴스 애널리스트다. 기사에 명시된 사실만 사용하고 사실과 해석을 분리한다. 관련성·중요도·영향 기간을 평가하되 추천 종합점수 조정은 -8~+8로 제한한다. 과장된 투자 표현을 쓰지 않는다."},
      {role:"user",content:JSON.stringify({symbol,company,sourceUrl:body.sourceUrl ?? null,article:text})},
    ], text:{format:{type:"json_schema",name:"news_analysis",strict:true,schema}},
  })});
  if (!response.ok) return Response.json({...analyzeNewsLocally(text,symbol,company),warning:"AI 호출 실패로 데모 엔진을 사용했습니다."});
  const payload = await response.json() as Record<string,unknown>; const parsed = outputText(payload);
  if (!parsed) return Response.json({...analyzeNewsLocally(text,symbol,company),warning:"AI 응답을 읽지 못해 데모 엔진을 사용했습니다."});
  return Response.json(JSON.parse(parsed) as NewsAnalysis);
}

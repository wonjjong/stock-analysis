"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Navigation } from "../components/Navigation";
import { stocks } from "../data";
import type { NewsAnalysis } from "../lib/news-analysis";

const samples = {
  positive: "삼성전자는 차세대 고대역폭메모리 공급 확대를 위한 고객사 품질 검증이 순조롭게 진행되고 있다고 밝혔다. 회사는 서버용 메모리 수요 회복과 제품 믹스 개선에 따라 하반기 반도체 부문 매출과 영업이익이 전년 동기보다 증가할 것으로 전망했다. 다만 구체적인 공급 계약 금액과 양산 시점은 공개하지 않았다.",
  negative: "삼성전자의 신규 파운드리 공정 양산 일정이 당초 계획보다 지연될 수 있다는 우려가 제기됐다. 일부 고객사의 제품 검증 기간이 길어지면서 관련 매출 반영 시점도 늦춰질 가능성이 있다. 회사는 공정 안정화 작업을 진행 중이며 확정된 일정 변경은 없다고 설명했다.",
};

export function NewsLab() {
  const [symbol,setSymbol] = useState("005930");
  const [sourceUrl,setSourceUrl] = useState("");
  const [text,setText] = useState(samples.positive);
  const [result,setResult] = useState<NewsAnalysis | null>(null);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const stock = stocks.find((item)=>item.symbol===symbol) ?? stocks[0];

  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const response = await fetch("/api/news/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol,company:stock.name,sourceUrl,text})});
      const payload = await response.json();
      if(!response.ok) throw new Error(payload.error ?? "분석에 실패했습니다.");
      setResult(payload);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "분석에 실패했습니다."); }
    finally { setLoading(false); }
  }

  return <div className="app-shell"><Navigation/><main className="main-area">
    <header className="topbar"><div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div><div className="live-pill"><i className="pulse-dot"/> NEWS INTELLIGENCE</div><div className="top-actions"><Link className="secondary-button" href={`/stock/${symbol}`}>{stock.name} 리서치</Link></div></header>
    <div className="content news-content">
      <section className="news-hero"><div><p className="eyebrow">NEWS ANALYSIS LAB</p><h1>헤드라인 너머의<br/><span>실제 영향을 판독합니다.</span></h1><p>단순 긍·부정을 넘어 종목 관련성, 실적 중요도, 반영 기간과 추천점수 조정 범위를 함께 계산합니다.</p></div><div className="news-method"><span>분석 원칙</span><ol><li><b>01</b> 사실과 해석 분리</li><li><b>02</b> 중복 기사보다 사건 중심</li><li><b>03</b> 점수 반영은 ±8점 이내</li></ol></div></section>
      <div className="news-workspace">
        <form className="news-input-panel" onSubmit={submit}>
          <div className="panel-title"><div><span className="eyebrow">ARTICLE INPUT</span><h2>분석할 뉴스</h2></div><span className="updated">40자 이상</span></div>
          <label>관련 종목<select value={symbol} onChange={(event)=>{setSymbol(event.target.value);setResult(null);}}>{stocks.map((item)=><option key={item.symbol} value={item.symbol}>{item.name} · {item.symbol}</option>)}</select></label>
          <label>출처 URL <small>선택 입력</small><input value={sourceUrl} onChange={(event)=>setSourceUrl(event.target.value)} placeholder="https://..." type="url"/></label>
          <label>기사 제목·본문<textarea value={text} onChange={(event)=>setText(event.target.value)} rows={12} placeholder="뉴스 제목과 본문을 붙여넣으세요."/></label>
          <div className="sample-actions"><span>샘플 불러오기</span><button type="button" onClick={()=>{setText(samples.positive);setResult(null);}}>긍정 뉴스</button><button type="button" onClick={()=>{setText(samples.negative);setResult(null);}}>부정 뉴스</button></div>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button analyze-button" disabled={loading || text.trim().length<40}>{loading ? "뉴스 근거 판독 중…" : "뉴스 분석하기 →"}</button>
          <p className="input-note">URL은 출처 기록용입니다. 현재 버전은 저작권과 크롤링 약관 문제를 피하기 위해 사용자가 붙여넣은 본문을 분석합니다.</p>
        </form>

        <section className="news-result-panel" aria-live="polite">
          {!result ? <div className="empty-analysis"><span className="ai-orbit">AI</span><h2>분석 결과가 여기에 표시됩니다.</h2><p>왼쪽의 샘플 뉴스로 바로 시험할 수 있습니다. OpenAI 키가 없으면 규칙 기반 데모 엔진이 사용됩니다.</p><div className="empty-grid"><span>관련성</span><span>중요도</span><span>감성</span><span>영향 기간</span></div></div> : <>
            <div className="result-head"><div><span className="eyebrow">ANALYSIS RESULT</span><h2>{stock.name} · {result.eventType}</h2><p>{result.summary}</p></div><div className={`sentiment-seal ${result.sentiment === "긍정" ? "positive-seal" : result.sentiment === "부정" ? "negative-seal" : "neutral-seal"}`}><strong>{result.sentiment}</strong><span>{result.sentimentScore}/100</span></div></div>
            <div className="news-score-grid"><article><span>종목 관련성</span><strong>{Math.round(result.relevance)}%</strong><i><b style={{width:`${result.relevance}%`}}/></i></article><article><span>중요도</span><strong>{result.materiality}</strong><small>실적 반영 기준</small></article><article><span>영향 기간</span><strong>{result.impactHorizon}</strong><small>시장 소화 예상</small></article><article><span>추천점수 조정</span><strong className={result.scoreAdjustment>0?"positive":result.scoreAdjustment<0?"negative":"neutral"}>{result.scoreAdjustment>0?"+":""}{result.scoreAdjustment}점</strong><small>상한 ±8점</small></article></div>
            <div className="evidence-box"><h3>기사에서 확인한 핵심 근거</h3>{result.keyEvidence.map((item,index)=><blockquote key={item}><b>0{index+1}</b><span>{item}</span></blockquote>)}</div>
            <div className="case-grid"><article><span className="positive">BULL CASE</span><p>{result.bullCase}</p></article><article><span className="negative">BEAR CASE</span><p>{result.bearCase}</p></article></div>
            <div className="watch-box"><div><h3>다음 확인 항목</h3><span className="engine-badge">{result.engine} · 신뢰도 {Math.round(result.confidence)}%</span></div><ul>{result.watchItems.map((item)=><li key={item}>{item}</li>)}</ul></div>
          </>}
        </section>
      </div>
      <p className="disclaimer">뉴스 평가는 기사 작성자의 표현을 투자 사실로 간주하지 않습니다. 회사 공시와 후속 실적 데이터로 교차검증해야 합니다.</p>
    </div>
  </main></div>;
}

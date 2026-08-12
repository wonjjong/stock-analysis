"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Navigation } from "./components/Navigation";
import { formatPrice, macro, portfolio, stocks, type Market } from "./data";

export function Dashboard() {
  const [market, setMarket] = useState<Market>("KR");
  const [query, setQuery] = useState("");
  const [saved, setSaved] = useState(["005930", "MSFT", "GOOGL"]);
  const recommendations = stocks.filter((stock) => stock.market === market).slice(0, 5);
  const searchResults = useMemo(() => {
    if (!query.trim()) return [];
    const normalized = query.toLowerCase();
    return stocks.filter((stock) => stock.name.toLowerCase().includes(normalized) || stock.symbol.toLowerCase().includes(normalized)).slice(0, 5);
  }, [query]);

  const totalKRW = portfolio.reduce((sum, item) => sum + item.qty * item.price * (item.currency === "USD" ? 1409.94 : 1), 0);
  const costKRW = portfolio.reduce((sum, item) => sum + item.qty * item.avg * (item.currency === "USD" ? 1409.94 : 1), 0);
  const pnl = totalKRW - costKRW;

  function toggleSaved(symbol: string) {
    setSaved((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]);
  }

  return (
    <div className="app-shell">
      <Navigation />
      <main className="main-area">
        <header className="topbar">
          <div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div>
          <div className="search-wrap">
            <span>⌕</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="종목명 또는 티커 검색" aria-label="종목 검색" />
            <kbd>⌘ K</kbd>
            {searchResults.length > 0 && (
              <div className="search-results">
                {searchResults.map((stock) => (
                  <Link href={`/stock/${stock.symbol}`} key={stock.symbol}>
                    <span><strong>{stock.name}</strong><small>{stock.exchange} · {stock.symbol}</small></span>
                    <b className={stock.change >= 0 ? "up" : "down"}>{stock.change >= 0 ? "+" : ""}{stock.change}%</b>
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div className="top-actions"><span className="live-pill"><i /> LIVE</span><button className="icon-button" aria-label="알림">◌</button></div>
        </header>

        <div className="content">
          <section className="hero-grid">
            <div>
              <p className="eyebrow">THURSDAY · AUG 13</p>
              <h1>좋은 판단을 위한<br /><span>오늘의 시그널.</span></h1>
              <p className="hero-copy">가격과 뉴스만 보지 않습니다. 기업가치, 변동성, 환율과 금리까지 연결해 오늘의 투자 후보를 선별했습니다.</p>
            </div>
            <Link href="/portfolio" className="portfolio-card">
              <div className="card-top"><span>내 포트폴리오</span><b>상세보기 ↗</b></div>
              <strong>{Math.round(totalKRW).toLocaleString("ko-KR")}원</strong>
              <div className="portfolio-meta"><span className="up">+{Math.round(pnl).toLocaleString("ko-KR")}원</span><span>수익률 +{(pnl / costKRW * 100).toFixed(2)}%</span></div>
              <div className="allocation-bar"><i /><i /><i /></div>
              <div className="allocation-legend"><span>국내주식 65%</span><span>미국주식 35%</span></div>
            </Link>
          </section>

          <section className="macro-section" aria-label="시장 환경">
            <div className="section-heading compact"><div><span className="eyebrow">MARKET PULSE</span><h2>시장 환경</h2></div><span className="updated">8월 13일 02:18 KST</span></div>
            <div className="macro-grid">
              {macro.map((item) => <article className="macro-card" key={item.label}><span>{item.label}</span><strong>{item.value}</strong><div><b className={item.tone}>{item.change}</b><small>{item.note}</small></div></article>)}
            </div>
          </section>

          <section className="recommend-section">
            <div className="section-heading">
              <div><span className="eyebrow">DAILY RESEARCH</span><h2>오늘의 추천 종목</h2><p>무료 시점 보존 데이터와 균형형 Champion 모델 기준</p></div>
              <div className="segmented" role="group" aria-label="시장 선택"><button onClick={() => setMarket("KR")} className={market === "KR" ? "active" : ""}>한국</button><button onClick={() => setMarket("US")} className={market === "US" ? "active" : ""}>미국</button></div>
            </div>
            <div className="recommend-list">
              {recommendations.map((stock, index) => (
                <article className="stock-row" key={stock.symbol}>
                  <span className="rank">0{index + 1}</span>
                  <Link href={`/stock/${stock.symbol}`} className="stock-identity"><span className={`stock-logo logo-${index}`}>{stock.name.slice(0, 1)}</span><div><strong>{stock.name}</strong><small>{stock.exchange} · {stock.symbol} · {stock.sector}</small></div></Link>
                  <div className="stock-thesis"><span className={`action-badge ${stock.action === "매수 유효" ? "buy" : "watch"}`}>{stock.action}</span><p>{stock.thesis}</p></div>
                  <div className="stock-score"><span>종합점수</span><strong>{stock.score}</strong><div className="score-track"><i style={{ width: `${stock.score}%` }} /></div></div>
                  <div className="stock-price"><strong>{formatPrice(stock)}</strong><span className={stock.change >= 0 ? "up" : "down"}>{stock.change >= 0 ? "+" : ""}{stock.change.toFixed(2)}%</span></div>
                  <button className={saved.includes(stock.symbol) ? "save-button saved" : "save-button"} onClick={() => toggleSaved(stock.symbol)} aria-label={`${stock.name} 관심종목 ${saved.includes(stock.symbol) ? "해제" : "추가"}`}>{saved.includes(stock.symbol) ? "★" : "☆"}</button>
                </article>
              ))}
            </div>
            <p className="disclaimer">상위 후보 5개는 항상 표시되며, 매수 기준을 통과하지 못한 종목은 ‘관찰’로 구분됩니다. 투자 참고용 정보이며 수익을 보장하지 않습니다.</p>
          </section>

          <section className="bottom-grid">
            <article className="panel saved-panel"><div className="panel-title"><div><span className="eyebrow">WATCHLIST</span><h3>관심종목</h3></div><span>{saved.length}개 저장</span></div>{stocks.filter((stock) => saved.includes(stock.symbol)).map((stock) => <Link href={`/stock/${stock.symbol}`} key={stock.symbol} className="mini-stock"><span className="mini-logo">{stock.name.slice(0, 1)}</span><div><strong>{stock.name}</strong><small>{stock.symbol}</small></div><b>{formatPrice(stock)}</b><em className={stock.change >= 0 ? "up" : "down"}>{stock.change >= 0 ? "+" : ""}{stock.change}%</em></Link>)}</article>
            <article className="panel ai-panel"><div className="ai-orbit"><span>AI</span></div><div><span className="eyebrow">SENIOR ANALYST AGENT</span><h3>숫자를 넘어, 근거까지.</h3><p>재무제표·뉴스·수급과 거시환경을 하나의 투자 논리로 연결합니다. 목표가와 손절가는 정량 엔진이 계산하고 AI는 근거를 검증합니다.</p><Link href="/stock/005930" className="primary-button">삼성전자 분석 보기 <b>→</b></Link></div></article>
          </section>
        </div>
      </main>
    </div>
  );
}

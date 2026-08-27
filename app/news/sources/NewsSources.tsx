"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Navigation } from "../../components/Navigation";
import { stocks } from "../../data";

type Source = {
  id: number; name: string; url: string; resolved_url: string | null; symbol: string; company: string;
  crawl_hour_kst: number; is_active: number; last_status: string; last_error: string | null;
  last_crawled_at: number | null; next_crawl_at: number; article_count: number; run_count: number;
};
type Article = {
  id: number; source_id: number; symbol: string; title: string; canonical_url: string; published_at: number | null;
  collected_at: number; sentiment: string; sentiment_score: number; materiality: string; relevance: number;
  event_type: string; score_adjustment: number; analysis_summary: string; source_name: string;
};

function when(value: number | null) {
  if (!value) return "아직 없음";
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" }).format(new Date(value));
}

export function NewsSources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [symbol, setSymbol] = useState("005930");
  const [hour, setHour] = useState(6);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const stock = stocks.find((item) => item.symbol === symbol) ?? stocks[0];

  const load = useCallback(async () => {
    const response = await fetch("/api/news/sources", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? "수집 현황을 불러오지 못했습니다.");
    setSources(payload.sources); setArticles(payload.articles);
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/api/news/sources", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "수집 현황을 불러오지 못했습니다.");
        return payload;
      })
      .then((payload) => { if (active) { setSources(payload.sources); setArticles(payload.articles); } })
      .catch((reason) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function addSource(event: FormEvent) {
    event.preventDefault(); setBusy("add"); setError(""); setNotice("");
    try {
      const response = await fetch("/api/news/sources", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, url, symbol, company: stock.name, crawlHourKst: hour }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "등록에 실패했습니다.");
      setUrl(""); setName("");
      setNotice(payload.warning ? `URL은 저장됐지만 첫 수집은 실패했습니다: ${payload.warning}` : `등록과 첫 수집이 완료됐습니다. 매일 ${hour}시에 다시 수집합니다.`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "등록에 실패했습니다."); }
    finally { setBusy(null); }
  }

  async function action(source: Source, kind: "crawl" | "toggle" | "delete") {
    if (kind === "delete" && !window.confirm(`‘${source.name}’과 연결된 수집 기사를 모두 삭제할까요?`)) return;
    setBusy(`${kind}-${source.id}`); setError(""); setNotice("");
    try {
      const endpoint = kind === "crawl" ? `/api/news/sources/${source.id}/crawl` : `/api/news/sources/${source.id}`;
      const response = await fetch(endpoint, {
        method: kind === "delete" ? "DELETE" : kind === "toggle" ? "PATCH" : "POST",
        headers: kind === "toggle" ? { "Content-Type": "application/json" } : undefined,
        body: kind === "toggle" ? JSON.stringify({ isActive: !source.is_active }) : undefined,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "작업에 실패했습니다.");
      setNotice(kind === "crawl" ? `${payload.fetchedCount}개 확인, 새 기사 ${payload.insertedCount}개 저장` : kind === "delete" ? "소스와 연결된 기사를 삭제했습니다." : source.is_active ? "자동 수집을 중지했습니다." : "자동 수집을 다시 시작했습니다.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "작업에 실패했습니다."); }
    finally { setBusy(null); }
  }

  return <div className="app-shell"><Navigation/><main className="main-area">
    <header className="topbar"><div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div><div className="live-pill"><i className="pulse-dot"/> DAILY CRAWLER</div><div className="top-actions"><Link className="secondary-button" href="/news">본문 직접 분석</Link></div></header>
    <div className="content source-content">
      <section className="source-hero"><div><p className="eyebrow">AUTOMATED NEWS PIPELINE</p><h1>URL만 등록하면<br/><span>매일 뉴스가 쌓입니다.</span></h1><p>RSS·Atom을 우선 탐지하고 제목·요약·발행일을 저장합니다. 같은 기사 URL은 중복 저장하지 않으며 수집 즉시 종목 영향도를 판독합니다.</p></div><div className="pipeline-strip"><span>URL 등록</span><b>→</b><span>매일 수집</span><b>→</b><span>중복 제거</span><b>→</b><span>DB + 분석</span></div></section>

      <section className="source-grid">
        <form className="source-form panel" onSubmit={addSource}>
          <div className="panel-title"><div><p className="eyebrow">NEW SOURCE</p><h2>뉴스 소스 등록</h2></div><span className="status-badge ready">매일 1회</span></div>
          <label>소스 이름 <small>선택</small><input value={name} onChange={(event) => setName(event.target.value)} placeholder="예: Reuters Technology"/></label>
          <label>RSS 또는 뉴스 목록 URL<input required type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/feed.xml"/></label>
          <label>연결 종목<select value={symbol} onChange={(event) => setSymbol(event.target.value)}>{stocks.map((item) => <option key={item.symbol} value={item.symbol}>{item.name} · {item.symbol}</option>)}</select></label>
          <label>매일 수집 시간 <small>한국시간</small><select value={hour} onChange={(event) => setHour(Number(event.target.value))}>{Array.from({ length: 24 }, (_, value) => <option key={value} value={value}>{String(value).padStart(2, "0")}:00</option>)}</select></label>
          <button className="primary-button source-submit" disabled={busy === "add" || !url}>{busy === "add" ? "피드 확인·첫 수집 중…" : "등록하고 지금 첫 수집 →"}</button>
          <p className="source-note">일반 페이지도 RSS 링크가 선언되어 있으면 자동으로 발견합니다. 로그인이 필요한 페이지·유료 기사·내부망 주소는 수집하지 않습니다.</p>
        </form>

        <div className="source-overview panel">
          <div className="panel-title"><div><p className="eyebrow">COLLECTION STATUS</p><h2>자동 수집 현황</h2></div><span className="updated">{loading ? "불러오는 중" : `${sources.filter((item) => item.is_active).length}개 실행 중`}</span></div>
          {(notice || error) && <p className={error ? "source-alert error" : "source-alert"}>{error || notice}</p>}
          {!loading && !sources.length ? <div className="source-empty"><span>＋</span><strong>등록된 뉴스 소스가 없습니다.</strong><p>왼쪽에서 첫 RSS URL을 등록하면 즉시 한 번 수집하고 이후 매일 자동 실행합니다.</p></div> : <div className="source-list">{sources.map((source) => <article className="source-row" key={source.id}>
            <div className="source-main"><div><span className={`status-dot ${source.last_status === "오류" ? "failed" : source.is_active ? "active" : "paused"}`}/><strong>{source.name}</strong><small>{source.company} · {source.symbol}</small></div><a href={source.resolved_url || source.url} target="_blank" rel="noreferrer">{source.resolved_url || source.url}</a>{source.last_error && <p>{source.last_error}</p>}</div>
            <div className="source-stats"><span><small>저장 기사</small><strong>{source.article_count}</strong></span><span><small>마지막 실행</small><strong>{when(source.last_crawled_at)}</strong></span><span><small>다음 실행</small><strong>{source.is_active ? when(source.next_crawl_at) : "중지됨"}</strong></span></div>
            <div className="source-actions"><button onClick={() => action(source, "crawl")} disabled={busy !== null}>{busy === `crawl-${source.id}` ? "수집 중" : "지금 수집"}</button><button onClick={() => action(source, "toggle")} disabled={busy !== null}>{source.is_active ? "중지" : "재개"}</button><button className="danger" onClick={() => action(source, "delete")} disabled={busy !== null}>삭제</button></div>
          </article>)}</div>}
        </div>
      </section>

      <section className="article-panel panel">
        <div className="panel-title"><div><p className="eyebrow">LATEST INGESTION</p><h2>최근 저장·분석된 기사</h2></div><span className="updated">URL 기준 중복 제거</span></div>
        {!articles.length ? <p className="article-empty">수집된 기사가 아직 없습니다.</p> : <div className="article-table"><div className="article-row article-header"><span>기사</span><span>분석</span><span>중요도</span><span>점수 반영</span></div>{articles.map((article) => <a className="article-row" key={article.id} href={article.canonical_url} target="_blank" rel="noreferrer"><span><strong>{article.title}</strong><small>{article.source_name} · {when(article.published_at || article.collected_at)}</small></span><span className={article.sentiment === "긍정" ? "positive" : article.sentiment === "부정" ? "negative" : "neutral"}>{article.sentiment} {article.sentiment_score}</span><span>{article.materiality} · 관련성 {article.relevance}%</span><span className={article.score_adjustment > 0 ? "positive" : article.score_adjustment < 0 ? "negative" : "neutral"}>{article.score_adjustment > 0 ? "+" : ""}{article.score_adjustment}점</span></a>)}</div>}
      </section>
      <p className="disclaimer">공식 RSS와 사이트가 허용한 공개 피드를 우선 사용합니다. 원문 전체를 재게시하지 않고 분석에 필요한 제목·요약·출처 링크만 보관합니다.</p>
    </div>
  </main></div>;
}

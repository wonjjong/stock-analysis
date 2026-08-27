"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Navigation } from "../../components/Navigation";

type Source = {
  id: number; name: string; url: string; resolved_url: string | null; category: string;
  crawl_hour_kst: number; is_active: number; last_status: string; last_error: string | null;
  last_crawled_at: number | null; next_crawl_at: number; article_count: number; today_article_count: number; run_count: number;
};
type Article = {
  id: number; source_id: number; title: string; canonical_url: string; published_at: number | null; published_date_kst: string;
  collected_at: number; sentiment: string; sentiment_score: number; materiality: string;
  event_type: string; score_adjustment: number; analysis_summary: string; source_name: string;
};

const categories = ["종합", "경제", "증권", "산업", "글로벌", "테크"];

function when(value: number | null) {
  if (!value) return "아직 없음";
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" }).format(new Date(value));
}

export function NewsSources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [articles, setArticles] = useState<Article[]>([]);
  const [collectionDate, setCollectionDate] = useState("");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState("종합");
  const [hour, setHour] = useState(6);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/news/sources", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? "수집 현황을 불러오지 못했습니다.");
    setSources(payload.sources); setArticles(payload.articles); setCollectionDate(payload.date);
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/api/news/sources", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "수집 현황을 불러오지 못했습니다.");
        return payload;
      })
      .then((payload) => { if (active) { setSources(payload.sources); setArticles(payload.articles); setCollectionDate(payload.date); } })
      .catch((reason) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function addSource(event: FormEvent) {
    event.preventDefault(); setBusy("add"); setError(""); setNotice("");
    try {
      const response = await fetch("/api/news/sources", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, url, category, crawlHourKst: hour }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "등록에 실패했습니다.");
      setUrl(""); setName("");
      setNotice(payload.warning ? `URL은 저장됐지만 첫 수집은 실패했습니다: ${payload.warning}` : `오늘 기사 ${payload.crawl.fetchedCount}개를 확인했습니다. 매일 ${hour}시에 다시 수집합니다.`);
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
      setNotice(kind === "crawl" ? `오늘 기사 ${payload.fetchedCount}개 확인, 신규 ${payload.insertedCount}개 저장` : kind === "delete" ? "사이트와 저장된 기사를 삭제했습니다." : source.is_active ? "자동 수집을 중지했습니다." : "자동 수집을 다시 시작했습니다.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "작업에 실패했습니다."); }
    finally { setBusy(null); }
  }

  return <div className="app-shell"><Navigation/><main className="main-area">
    <header className="topbar"><div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div><div className="live-pill"><i className="pulse-dot"/> DAILY CRAWLER</div><div className="top-actions"><Link className="secondary-button" href="/news">본문 직접 분석</Link></div></header>
    <div className="content source-content">
      <section className="source-hero"><div><p className="eyebrow">DAILY NEWS SCRAPER</p><h1>뉴스 사이트를 돌며<br/><span>오늘 기사만 저장합니다.</span></h1><p>뉴스 목록 URL에 접속해 한국시간 오늘 날짜의 기사만 추출합니다. RSS·Atom, JSON-LD와 HTML 시간 태그를 자동 판독하고 같은 기사 URL은 중복 저장하지 않습니다.</p></div><div className="pipeline-strip"><span>사이트 접속</span><b>→</b><span>오늘 날짜 판독</span><b>→</b><span>중복 제거</span><b>→</b><span>DB 저장</span></div></section>

      <section className="source-grid">
        <form className="source-form panel" onSubmit={addSource}>
          <div className="panel-title"><div><p className="eyebrow">NEW SOURCE</p><h2>뉴스 소스 등록</h2></div><span className="status-badge ready">매일 1회</span></div>
          <label>소스 이름 <small>선택</small><input value={name} onChange={(event) => setName(event.target.value)} placeholder="예: Reuters Technology"/></label>
          <label>뉴스 사이트·목록 URL<input required type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://news.example.com/latest"/></label>
          <label>뉴스 분류<select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>매일 수집 시간 <small>한국시간</small><select value={hour} onChange={(event) => setHour(Number(event.target.value))}>{Array.from({ length: 24 }, (_, value) => <option key={value} value={value}>{String(value).padStart(2, "0")}:00</option>)}</select></label>
          <button className="primary-button source-submit" disabled={busy === "add" || !url}>{busy === "add" ? "사이트 접속·오늘 기사 수집 중…" : "등록하고 오늘 기사 수집 →"}</button>
          <p className="source-note">페이지에 표시된 발행일을 기준으로 오늘 기사만 저장합니다. RSS가 있으면 자동 사용하며 JSON-LD·HTML 시간 태그도 읽습니다. robots.txt가 금지한 경로와 로그인·유료·내부망 페이지는 제외합니다.</p>
        </form>

        <div className="source-overview panel">
          <div className="panel-title"><div><p className="eyebrow">COLLECTION STATUS</p><h2>자동 수집 현황</h2></div><span className="updated">{loading ? "불러오는 중" : `${sources.filter((item) => item.is_active).length}개 실행 중`}</span></div>
          {(notice || error) && <p className={error ? "source-alert error" : "source-alert"}>{error || notice}</p>}
          {!loading && !sources.length ? <div className="source-empty"><span>＋</span><strong>등록된 뉴스 사이트가 없습니다.</strong><p>왼쪽에서 뉴스 목록 URL을 등록하면 오늘 기사만 즉시 수집하고 이후 매일 자동 실행합니다.</p></div> : <div className="source-list">{sources.map((source) => <article className="source-row" key={source.id}>
            <div className="source-main"><div><span className={`status-dot ${source.last_status === "오류" ? "failed" : source.is_active ? "active" : "paused"}`}/><strong>{source.name}</strong><small>{source.category} · {source.last_status}</small></div><a href={source.url} target="_blank" rel="noreferrer">{source.url}</a>{source.last_error && <p>{source.last_error}</p>}</div>
            <div className="source-stats"><span><small>오늘 / 누적</small><strong>{source.today_article_count} / {source.article_count}</strong></span><span><small>마지막 실행</small><strong>{when(source.last_crawled_at)}</strong></span><span><small>다음 실행</small><strong>{source.is_active ? when(source.next_crawl_at) : "중지됨"}</strong></span></div>
            <div className="source-actions"><button onClick={() => action(source, "crawl")} disabled={busy !== null}>{busy === `crawl-${source.id}` ? "수집 중" : "지금 수집"}</button><button onClick={() => action(source, "toggle")} disabled={busy !== null}>{source.is_active ? "중지" : "재개"}</button><button className="danger" onClick={() => action(source, "delete")} disabled={busy !== null}>삭제</button></div>
          </article>)}</div>}
        </div>
      </section>

      <section className="article-panel panel">
        <div className="panel-title"><div><p className="eyebrow">TODAY&apos;S INGESTION</p><h2>{collectionDate || "오늘"} 저장 기사</h2></div><span className="updated">한국시간 · URL 중복 제거</span></div>
        {!articles.length ? <p className="article-empty">오늘 날짜로 저장된 기사가 아직 없습니다.</p> : <div className="article-table"><div className="article-row article-header"><span>기사</span><span>감성</span><span>유형·중요도</span><span>시장 신호</span></div>{articles.map((article) => <a className="article-row" key={article.id} href={article.canonical_url} target="_blank" rel="noreferrer"><span><strong>{article.title}</strong><small>{article.source_name} · {when(article.published_at || article.collected_at)}</small></span><span className={article.sentiment === "긍정" ? "positive" : article.sentiment === "부정" ? "negative" : "neutral"}>{article.sentiment} {article.sentiment_score}</span><span>{article.event_type} · {article.materiality}</span><span className={article.score_adjustment > 0 ? "positive" : article.score_adjustment < 0 ? "negative" : "neutral"}>{article.score_adjustment > 0 ? "+" : ""}{article.score_adjustment}</span></a>)}</div>}
      </section>
      <p className="disclaimer">robots.txt가 허용한 공개 목록·RSS와 발행일 정보만 수집합니다. 원문 전체를 재게시하지 않고 제목·요약·발행시각·출처 링크만 DB에 보관합니다.</p>
    </div>
  </main></div>;
}

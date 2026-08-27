"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigation } from "../../components/Navigation";

type SymbolTag = { symbol: string; company: string; market: string; sector: string; relevance: number };
type Article = {
  id: number; source_id: number; title: string; canonical_url: string; excerpt: string;
  published_at: number | null; collected_at: number; date_kst: string; sentiment: string; sentiment_score: number;
  materiality: string; relevance: number; event_type: string; score_adjustment: number;
  source_name: string; source_category: string; insight_status: string;
  summary: string | null; keywords: string[] | null; sectors: string[] | null; evidence: string[] | null;
  market_view: string | null; impact_horizon: string | null; engine: string | null; model: string | null;
  body_chars: number | null; symbols: SymbolTag[];
};
type Source = { id: number; name: string; category: string; article_count: number };
type TopSymbol = { symbol: string; company: string; market: string; article_count: number };
type Summary = { total: number; positive: number; negative: number; pending: number; firstDate: string | null; lastDate: string | null };
type Filters = { q: string; from: string; to: string; source: string; sentiment: string; symbol: string };

const emptyFilters: Filters = { q: "", from: "", to: "", source: "", sentiment: "", symbol: "" };
const sentiments = ["긍정", "중립", "부정"];
const presets = [
  { label: "오늘", days: 0 },
  { label: "7일", days: 6 },
  { label: "30일", days: 29 },
  { label: "전체", days: -1 },
];

function dateKst(offsetDays = 0) {
  return new Date(Date.now() + 9 * 60 * 60 * 1000 - offsetDays * 86_400_000).toISOString().slice(0, 10);
}

function when(value: number | null) {
  if (!value) return "시각 미상";
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" }).format(new Date(value));
}

function sentimentClass(value: string) {
  return value === "긍정" ? "positive" : value === "부정" ? "negative" : "neutral";
}

// keywords·sectors·evidence는 jsonb 컬럼이라 드라이버가 이미 파싱해 배열로 준다.
// JSON.parse를 그대로 두면 배열을 문자열로 취급해 전부 빈 배열로 떨어진다.
function list(value: string[] | null) {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

export function NewsArchive() {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  const [articles, setArticles] = useState<Article[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [topSymbols, setTopSymbols] = useState<TopSymbol[]>([]);
  const [summary, setSummary] = useState<Summary>({ total: 0, positive: 0, negative: 0, pending: 0, firstDate: null, lastDate: null });
  const [analyzing, setAnalyzing] = useState(false);
  const [notice, setNotice] = useState("");
  const [pageCount, setPageCount] = useState(1);
  const [loadedKey, setLoadedKey] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useMemo(() => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
    return params.toString();
  }, [filters]);
  const [refreshes, setRefreshes] = useState(0);
  const query = `${search}&page=${page}`;
  const requestKey = `${query}#${refreshes}`;
  const loading = loadedKey !== requestKey;

  const update = useCallback((patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  }, []);

  // 키 입력마다 조회하지 않도록 300ms 뒤에만 키워드 필터를 갱신한다.
  const changeTerm = useCallback((value: string) => {
    setTerm(value);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => update({ q: value.trim() }), 300);
  }, [update]);

  useEffect(() => () => { if (debounce.current) clearTimeout(debounce.current); }, []);

  useEffect(() => {
    let active = true;
    fetch(`/api/news/articles?${query}`, { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "기사를 불러오지 못했습니다.");
        return payload;
      })
      .then((payload) => {
        if (!active) return;
        setArticles(payload.articles); setSources(payload.sources); setSummary(payload.summary);
        setTopSymbols(payload.topSymbols ?? []); setPageCount(payload.pageCount);
        setError(""); setOpen(null); setLoadedKey(requestKey);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "기사를 불러오지 못했습니다.");
        setArticles([]); setLoadedKey(requestKey);
      });
    return () => { active = false; };
  }, [query, requestKey]);

  const analyze = useCallback(async () => {
    setAnalyzing(true); setNotice(""); setError("");
    try {
      const response = await fetch("/api/news/insights", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: 20 }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "본문 분석에 실패했습니다.");
      setNotice(`${payload.done}건 분석 완료 (AI ${payload.llm}건 · 규칙 ${payload.rule}건${payload.failed ? ` · 실패 ${payload.failed}건` : ""}). 남은 대기 ${payload.queue.pending}건.`);
      setRefreshes((current) => current + 1);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "본문 분석에 실패했습니다."); }
    finally { setAnalyzing(false); }
  }, []);

  const applyPreset = useCallback((days: number) => {
    update(days < 0 ? { from: "", to: "" } : { from: dateKst(days), to: dateKst(0) });
  }, [update]);

  const activePreset = presets.find((preset) => preset.days < 0 ? !filters.from && !filters.to : filters.from === dateKst(preset.days) && filters.to === dateKst(0));
  const dirty = Boolean(filters.q || filters.from || filters.to || filters.source || filters.sentiment);

  return <div className="app-shell"><Navigation/><main className="main-area">
    <header className="topbar"><div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div><div className="live-pill"><i className="pulse-dot"/> NEWS ARCHIVE</div><div className="top-actions"><Link className="secondary-button" href="/news/sources">수집 소스 관리</Link><Link className="secondary-button" href="/news">본문 직접 분석</Link></div></header>
    <div className="content archive-content">
      <section className="archive-hero"><div><p className="eyebrow">COLLECTED ARTICLE ARCHIVE</p><h1>수집한 모든 기사를<br/><span>날짜와 소스로 찾습니다.</span></h1><p>크롤러가 저장한 기사를 기간·소스·감성·키워드로 좁혀 봅니다. 행을 펼치면 요약과 시장 영향 분석을, 제목을 누르면 원문을 확인할 수 있습니다.</p></div>
        <div className="archive-summary">
          <span><small>검색 결과</small><strong>{summary.total.toLocaleString()}건</strong></span>
          <span><small>긍정</small><strong className="positive">{summary.positive.toLocaleString()}</strong></span>
          <span><small>부정</small><strong className="negative">{summary.negative.toLocaleString()}</strong></span>
          <span><small>본문 분석 대기</small><strong>{summary.pending.toLocaleString()}건</strong></span>
          <span><small>수집 기간</small><strong>{summary.firstDate ? `${summary.firstDate} ~ ${summary.lastDate}` : "없음"}</strong></span>
        </div>
      </section>

      <section className="archive-filters panel">
        <div className="filter-row">
          <label className="filter-search">키워드<input value={term} onChange={(event) => changeTerm(event.target.value)} placeholder="제목·요약·분석 내용 검색"/></label>
          <label>시작일<input type="date" max={filters.to || undefined} value={filters.from} onChange={(event) => update({ from: event.target.value })}/></label>
          <label>종료일<input type="date" min={filters.from || undefined} value={filters.to} onChange={(event) => update({ to: event.target.value })}/></label>
          <label>소스<select value={filters.source} onChange={(event) => update({ source: event.target.value })}><option value="">전체 소스</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.name} ({source.article_count})</option>)}</select></label>
          <label>종목<select value={filters.symbol} onChange={(event) => update({ symbol: event.target.value })}><option value="">전체 종목</option>{topSymbols.map((item) => <option key={item.symbol} value={item.symbol}>{item.company} ({item.article_count})</option>)}</select></label>
          <label>감성<select value={filters.sentiment} onChange={(event) => update({ sentiment: event.target.value })}><option value="">전체</option>{sentiments.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        </div>
        <div className="filter-actions">
          <div className="segmented">{presets.map((preset) => <button key={preset.label} type="button" className={activePreset?.label === preset.label ? "active" : ""} onClick={() => applyPreset(preset.days)}>{preset.label}</button>)}</div>
          <button type="button" className="reset-filters" disabled={!dirty} onClick={() => { setTerm(""); update(emptyFilters); }}>필터 초기화</button>
        </div>
      </section>

      <section className="article-panel panel">
        <div className="panel-title"><div><p className="eyebrow">ARCHIVED ARTICLES</p><h2>{loading ? "불러오는 중" : `${summary.total.toLocaleString()}건 중 ${articles.length}건 표시`}</h2></div><div className="panel-tools"><span className="updated">한국시간 · 최신순</span><button type="button" className="secondary-button" disabled={analyzing || !summary.pending} onClick={analyze}>{analyzing ? "본문 분석 중…" : `본문 분석 실행 (대기 ${summary.pending})`}</button></div></div>
        {(notice || error) && <p className={error ? "source-alert error" : "source-alert"}>{error || notice}</p>}
        {!loading && !articles.length ? <p className="article-empty">{dirty ? "조건에 맞는 기사가 없습니다. 기간이나 키워드를 바꿔보세요." : "저장된 기사가 아직 없습니다. 수집 소스를 등록하면 여기에 쌓입니다."}</p> : <div className="article-table">
          <div className="article-row archive-row article-header"><span>기사</span><span>날짜</span><span>감성</span><span>유형·중요도</span><span>신호</span></div>
          {articles.map((article) => <div className="archive-item" key={article.id}>
            <button type="button" className="article-row archive-row" aria-expanded={open === article.id} onClick={() => setOpen(open === article.id ? null : article.id)}>
              <span><strong>{article.title}</strong><small>{article.source_name} · {article.source_category} · {when(article.published_at || article.collected_at)}{article.symbols.length ? ` · ${article.symbols.map((item) => item.company).join(", ")}` : ""}</small></span>
              <span>{article.date_kst}</span>
              <span className={sentimentClass(article.sentiment)}>{article.sentiment} {article.sentiment_score}</span>
              <span>{article.event_type} · {article.materiality}</span>
              <span className={article.score_adjustment > 0 ? "positive" : article.score_adjustment < 0 ? "negative" : "neutral"}>{article.score_adjustment > 0 ? "+" : ""}{article.score_adjustment}</span>
            </button>
            {open === article.id && <div className="archive-detail">
              {article.summary ? <p className="archive-summary-text">{article.summary}</p> : <p className="archive-summary-text muted">아직 본문 분석 전입니다. {article.excerpt || "저장된 요약이 없습니다."}</p>}
              {Boolean(article.symbols.length) && <div className="chip-row">{article.symbols.map((item) => <button key={item.symbol} type="button" className="chip symbol-chip" onClick={() => update({ symbol: item.symbol })}>{item.company} <small>{item.symbol} · 관련도 {item.relevance}</small></button>)}</div>}
              {Boolean(list(article.keywords).length) && <div className="chip-row">{list(article.keywords).map((item) => <button key={item} type="button" className="chip" onClick={() => { setTerm(item); update({ q: item }); }}>#{item}</button>)}</div>}
              {article.market_view && <p className="archive-analysis"><b>시장 관점</b> {article.market_view}</p>}
              {Boolean(list(article.sectors).length) && <p className="archive-analysis"><b>영향 업종</b> {list(article.sectors).join(", ")}</p>}
              {Boolean(list(article.evidence).length) && <ul className="evidence-list">{list(article.evidence).map((item) => <li key={item}>{item}</li>)}</ul>}
              <div className="archive-detail-meta">
                <span>{article.impact_horizon ?? "영향 기간 미상"}</span>
                <span>{article.engine ? `${article.engine}${article.model ? ` · ${article.model}` : ""}` : "분석 대기"}</span>
                <span>본문 {article.body_chars ?? 0}자</span>
                <span>수집 {when(article.collected_at)}</span>
                <a href={article.canonical_url} target="_blank" rel="noreferrer">원문 열기 →</a>
              </div>
            </div>}
          </div>)}
        </div>}
        {pageCount > 1 && <div className="archive-pager">
          <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>← 이전</button>
          <span>{page} / {pageCount}</span>
          <button type="button" disabled={page >= pageCount || loading} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>다음 →</button>
        </div>}
      </section>
      <p className="disclaimer">제목·요약·발행시각·출처 링크만 보관합니다. 원문 전체는 각 언론사 페이지에서 확인하세요.</p>
    </div>
  </main></div>;
}

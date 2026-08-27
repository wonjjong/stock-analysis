"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Navigation } from "../../components/Navigation";

type Provider = {
  id: number; name: string; base_url: string; model: string; api_key: string; has_key: boolean;
  priority: number; is_active: boolean; daily_limit: number; used_today: number; usage_date_kst: string | null;
  cooldown_until: number | null; last_status: string; last_error: string | null; last_used_at: number | null;
  success_count: number; failure_count: number;
};
type Preset = { key: string; name: string; baseUrl: string; model: string; priority: number; dailyLimit: number; keyUrl: string; note: string };
type Draft = { name: string; baseUrl: string; model: string; apiKey: string; priority: number; dailyLimit: number; keyUrl: string; note: string };

const blank: Draft = { name: "", baseUrl: "", model: "", apiKey: "", priority: 100, dailyLimit: 0, keyUrl: "", note: "" };

function when(value: number | null) {
  if (!value) return "없음";
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" }).format(new Date(value));
}

function statusClass(provider: Provider, now: number) {
  if (!provider.is_active) return "paused";
  if (provider.cooldown_until && provider.cooldown_until > now) return "failed";
  return "active";
}

export function NewsProviders() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [draft, setDraft] = useState<Draft>(blank);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loadedAt, setLoadedAt] = useState(0);

  const load = useCallback(async () => {
    const response = await fetch("/api/news/providers", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? "공급자 목록을 불러오지 못했습니다.");
    setProviders(payload.providers); setPresets(payload.presets); setLoadedAt(Date.now());
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/api/news/providers", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "공급자 목록을 불러오지 못했습니다.");
        return payload;
      })
      .then((payload) => { if (active) { setProviders(payload.providers); setPresets(payload.presets); setLoadedAt(Date.now()); } })
      .catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy("add"); setError(""); setNotice("");
    try {
      const response = await fetch("/api/news/providers", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: draft.name, baseUrl: draft.baseUrl, model: draft.model, apiKey: draft.apiKey, priority: draft.priority, dailyLimit: draft.dailyLimit }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "등록에 실패했습니다.");
      setNotice(`${draft.name}을(를) 우선순위 ${draft.priority}로 등록했습니다. 연결 확인을 눌러 키가 도는지 보세요.`);
      setDraft(blank);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "등록에 실패했습니다."); }
    finally { setBusy(null); }
  }

  async function patch(provider: Provider, body: Record<string, unknown>, label: string, message: string) {
    setBusy(`${label}-${provider.id}`); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/news/providers/${provider.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "변경에 실패했습니다.");
      setNotice(message);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "변경에 실패했습니다."); }
    finally { setBusy(null); }
  }

  async function remove(provider: Provider) {
    if (!window.confirm(`‘${provider.name}’을(를) 삭제할까요? 저장된 API 키도 함께 지워집니다.`)) return;
    setBusy(`delete-${provider.id}`); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/news/providers/${provider.id}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "삭제에 실패했습니다.");
      setNotice("공급자를 삭제했습니다.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "삭제에 실패했습니다."); }
    finally { setBusy(null); }
  }

  async function verify(provider: Provider) {
    setBusy(`test-${provider.id}`); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/news/providers/${provider.id}/test`, { method: "POST" });
      const payload = await response.json();
      if (payload.ok) setNotice(`${provider.name} 연결 정상 (${payload.model}).`);
      else setError(`${provider.name} 연결 실패 · ${payload.kind ?? "오류"}: ${payload.error ?? "알 수 없는 오류"}`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "연결 확인에 실패했습니다."); }
    finally { setBusy(null); }
  }

  const usable = providers.filter((item) => item.is_active && item.has_key && !(item.cooldown_until && item.cooldown_until > loadedAt));

  return <div className="app-shell"><Navigation/><main className="main-area">
    <header className="topbar"><div className="mobile-brand"><span className="brand-mark">S</span><strong>signalist</strong></div><div className="live-pill"><i className="pulse-dot"/> AI FAILOVER CHAIN</div><div className="top-actions"><Link className="secondary-button" href="/news/archive">기사 아카이브</Link><Link className="secondary-button" href="/news/sources">수집 소스 관리</Link></div></header>
    <div className="content provider-content">
      <section className="provider-hero"><div><p className="eyebrow">FREE TIER FAILOVER</p><h1>무료 AI를 여러 개 걸어두고<br/><span>순서대로 넘겨 씁니다.</span></h1><p>우선순위가 낮은 숫자부터 호출합니다. 한도 초과나 인증 오류가 나면 그 공급자를 쉬게 하고 바로 다음 공급자로 넘어갑니다. 전부 막히면 규칙 기반 엔진으로 분석을 이어갑니다.</p></div>
        <div className="provider-stat"><span><small>등록</small><strong>{providers.length}개</strong></span><span><small>지금 사용 가능</small><strong className={usable.length ? "positive" : "negative"}>{usable.length}개</strong></span></div>
      </section>

      {(notice || error) && <p className={error ? "source-alert error" : "source-alert"}>{error || notice}</p>}

      <section className="provider-grid">
        <form className="panel provider-form" onSubmit={submit}>
          <div className="panel-title"><div><p className="eyebrow">NEW PROVIDER</p><h2>공급자 등록</h2></div><span className="status-badge ready">OpenAI 호환</span></div>
          <div className="preset-row">{presets.map((preset) => <button key={preset.key} type="button" className={draft.name === preset.name ? "chip active" : "chip"} onClick={() => setDraft({ ...blank, name: preset.name, baseUrl: preset.baseUrl, model: preset.model, priority: preset.priority, dailyLimit: preset.dailyLimit, keyUrl: preset.keyUrl, note: preset.note })}>{preset.name}</button>)}</div>
          {draft.note && <p className="preset-note">{draft.note} {draft.keyUrl && <a href={draft.keyUrl} target="_blank" rel="noreferrer">키 발급 →</a>}</p>}
          <label>표시 이름<input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="예: Google Gemini"/></label>
          <label>Base URL <small>OpenAI 호환 경로</small><input required type="url" value={draft.baseUrl} onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })} placeholder="https://.../v1"/></label>
          <label>모델명<input required value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} placeholder="gemini-2.5-flash"/></label>
          <label>API 키<input required type="password" autoComplete="off" value={draft.apiKey} onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })} placeholder="발급받은 키"/></label>
          <div className="form-pair">
            <label>우선순위 <small>낮을수록 먼저</small><input type="number" min={1} max={999} value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: Number(event.target.value) })}/></label>
            <label>일일 한도 <small>0이면 무제한</small><input type="number" min={0} value={draft.dailyLimit} onChange={(event) => setDraft({ ...draft, dailyLimit: Number(event.target.value) })}/></label>
          </div>
          <button className="primary-button provider-submit" disabled={busy === "add"}>{busy === "add" ? "저장 중…" : "공급자 등록 →"}</button>
          <p className="source-note">키는 DB에 저장되고 화면에는 끝 네 글자만 보여줍니다. 무료 티어는 보낸 내용이 모델 개선에 쓰일 수 있으니 공개된 기사 본문만 보냅니다.</p>
        </form>

        <div className="panel provider-list-panel">
          <div className="panel-title"><div><p className="eyebrow">FAILOVER ORDER</p><h2>호출 순서</h2></div><span className="updated">우선순위 오름차순</span></div>
          {!providers.length ? <div className="source-empty"><span>＋</span><strong>등록된 AI 공급자가 없습니다.</strong><p>왼쪽 프리셋에서 하나를 고르고 발급받은 키를 넣으면 본문 분석이 AI로 넘어갑니다. 그때까지는 규칙 기반으로만 동작합니다.</p></div>
          : <div className="provider-list">{providers.map((provider, index) => {
            const resting = Boolean(provider.cooldown_until && provider.cooldown_until > loadedAt);
            return <article className="provider-row" key={provider.id}>
              <div className="provider-main">
                <div><span className={`status-dot ${statusClass(provider, loadedAt)}`}/><strong>{index + 1}. {provider.name}</strong><small>{provider.model} · 우선순위 {provider.priority}</small></div>
                <p className="provider-url">{provider.base_url}</p>
                <p className="provider-key">키 {provider.has_key ? provider.api_key : "없음"}</p>
                {provider.last_error && <p className="provider-error">{provider.last_status} · {provider.last_error}</p>}
              </div>
              <div className="source-stats">
                <span><small>상태</small><strong className={resting ? "negative" : provider.is_active ? "positive" : ""}>{!provider.is_active ? "중지됨" : resting ? `휴식 ~${when(provider.cooldown_until)}` : provider.last_status}</strong></span>
                <span><small>오늘 사용</small><strong>{provider.used_today}{provider.daily_limit ? ` / ${provider.daily_limit}` : ""}</strong></span>
                <span><small>성공 / 실패</small><strong>{provider.success_count} / {provider.failure_count}</strong></span>
              </div>
              <div className="source-actions">
                <button onClick={() => verify(provider)} disabled={busy !== null || !provider.has_key}>{busy === `test-${provider.id}` ? "확인 중" : "연결 확인"}</button>
                <button onClick={() => patch(provider, { priority: provider.priority - 10 }, "up", `${provider.name} 우선순위를 올렸습니다.`)} disabled={busy !== null || provider.priority <= 1}>↑ 우선</button>
                <button onClick={() => patch(provider, { priority: provider.priority + 10 }, "down", `${provider.name} 우선순위를 내렸습니다.`)} disabled={busy !== null}>↓ 후순위</button>
                {resting && <button onClick={() => patch(provider, { clearCooldown: true }, "wake", `${provider.name}의 휴식을 해제했습니다.`)} disabled={busy !== null}>휴식 해제</button>}
                <button onClick={() => patch(provider, { isActive: !provider.is_active }, "toggle", provider.is_active ? "공급자를 중지했습니다." : "공급자를 다시 켰습니다.")} disabled={busy !== null}>{provider.is_active ? "중지" : "재개"}</button>
                <button className="danger" onClick={() => remove(provider)} disabled={busy !== null}>삭제</button>
              </div>
            </article>;
          })}</div>}
        </div>
      </section>
      <p className="disclaimer">공급자별 무료 한도와 모델명은 제공사가 수시로 바꿉니다. 연결 확인이 실패하면 모델명부터 최신 값으로 고쳐보세요.</p>
    </div>
  </main></div>;
}

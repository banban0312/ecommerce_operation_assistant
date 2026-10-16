"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { contentRequest, type ContentBundle, type ContentItem } from "@/lib/content";

function itemTitle(item: ContentItem) { return String(item.content.title ?? `${item.content_type} ${item.slot_key}`); }

export function ContentWorkbench({ productId, workspaceId }: { productId: number; workspaceId: number }) {
  const [bundle, setBundle] = useState<ContentBundle | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const load = useCallback(async () => {
    try { setBundle(await contentRequest<ContentBundle>(`products/${productId}`, workspaceId)); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "内容加载失败"); }
  }, [productId, workspaceId]);
  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(timer); }, [load]);

  async function generate(path: string) {
    setBusy(path); setError(""); setMessage("");
    try { const result = await contentRequest<{ message: string }>(`products/${productId}/${path}`, workspaceId, { method: "POST" }); setMessage(result.message); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "生成失败"); }
    finally { setBusy(""); }
  }
  function startEdit(item: ContentItem) { setEditing(item.id); setDraft(JSON.stringify(item.content, null, 2)); setMessage(""); }
  async function save(event: FormEvent<HTMLFormElement>, item: ContentItem) {
    event.preventDefault(); setBusy(String(item.id));
    try { const content = JSON.parse(draft) as Record<string, unknown>; await contentRequest(`content/${item.id}`, workspaceId, { method: "PATCH", body: JSON.stringify({ revision: item.revision, content }) }); setEditing(null); setMessage("人工修改已保存。"); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败：请输入合法 JSON"); }
    finally { setBusy(""); }
  }
  async function transition(item: ContentItem, action: "confirm" | "archive") {
    setBusy(String(item.id)); setError("");
    try { await contentRequest(`content/${item.id}/${action}`, workspaceId, { method: "POST" }); setMessage(action === "confirm" ? "版本已确认，后续生成会保留该版本。" : "版本已归档。"); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败"); }
    finally { setBusy(""); }
  }
  const all = bundle ? [...bundle.diagnosis, ...bundle.image_ideas, ...bundle.video_scripts] : [];
  return <section className="panel content-workbench" id="ai-content">
    <div className="section-heading"><div><p className="eyebrow">AI CONTENT STUDIO</p><h2>智能诊断与内容创意</h2></div><span className="muted-tag">可编辑 · 可确认 · 有版本</span></div>
    <p className="subtle">生成前会读取当前商品档案、SKU 和竞品；模型未配置或调用失败时不会覆盖已有版本。确认版本会被保留。</p>
    <div className="section-actions"><button className="button primary" disabled={!!busy} onClick={() => void generate("diagnosis")}>生成结构化诊断</button><button className="button secondary" disabled={!!busy} onClick={() => void generate("image-ideas")}>生成 3 组主图创意</button><button className="button secondary" disabled={!!busy} onClick={() => void generate("video-scripts")}>生成 3 套视频脚本</button></div>
    {message && <p className="notice success" role="status">{message}</p>}{error && <p className="notice error" role="alert">{error}</p>}
    {!bundle ? <p className="subtle">正在加载内容版本…</p> : !all.length ? <p className="empty-state">暂无内容版本，请先完善商品档案后生成。</p> : <div className="content-version-grid">{all.map((item) => <article className="content-version-card" key={item.id}><div className="sku-head"><div><small>{item.content_type === "diagnosis" ? "商品诊断" : item.content_type === "image_idea" ? `主图方向 ${item.slot_key}` : `视频脚本 ${item.slot_key}`}</small><h3>{itemTitle(item)}</h3></div><span className={`config-status ${item.status === "confirmed" ? "ready" : ""}`}>{item.status === "confirmed" ? "已确认" : item.status === "archived" ? "已归档" : "草稿 v" + item.version_no}</span></div>{editing === item.id ? <form className="content-editor" onSubmit={(event) => void save(event, item)}><textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={12} aria-label="内容 JSON 编辑器" /><div className="section-actions"><button className="button primary" disabled={busy === String(item.id)}>保存人工修改</button><button type="button" className="button secondary" onClick={() => setEditing(null)}>取消</button></div></form> : <><pre className="content-preview">{JSON.stringify(item.content, null, 2)}</pre><div className="section-actions"><button className="button secondary" disabled={item.status === "confirmed" || !!busy} onClick={() => startEdit(item)}>编辑</button>{item.status !== "confirmed" && <button className="button primary" disabled={!!busy} onClick={() => void transition(item, "confirm")}>确认版本</button>}{item.status !== "archived" && <button className="button secondary" disabled={!!busy} onClick={() => void transition(item, "archive")}>归档</button>}</div></>}</article>)}</div>}
  </section>;
}

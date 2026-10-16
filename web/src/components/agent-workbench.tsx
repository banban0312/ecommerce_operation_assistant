"use client";

import { useCallback, useEffect, useState } from "react";
import { agentRequest, type AgentTask, type AgentTool } from "@/lib/agent";
import { catalogRequest, type ProductList } from "@/lib/catalog";

export function AgentWorkbench({ workspaceId, initialProductId = "" }: { workspaceId: number; initialProductId?: string }) {
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [products, setProducts] = useState<ProductList["items"]>([]);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [productId, setProductId] = useState(initialProductId);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [productPickerOpen, setProductPickerOpen] = useState(false);
  const [productSearch, setProductSearch] = useState("");
  const [form, setForm] = useState({ name: "商品运营分析", goal: "分析商品经营表现并给出可执行建议" });

  const loadTasks = useCallback(async () => {
    if (!productId) { setTasks([]); return; }
    try {
      setTasks(await agentRequest<AgentTask[]>(`products/${productId}/tasks`, workspaceId));
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "任务加载失败"); }
  }, [productId, workspaceId]);
  const selectedProduct = products.find((product) => String(product.id) === productId);
  const visibleProducts = products.filter((product) =>
    `${product.name} ${product.category} ${product.id}`.toLocaleLowerCase().includes(productSearch.trim().toLocaleLowerCase()),
  );

  useEffect(() => {
    let active = true;
    Promise.all([
      agentRequest<AgentTool[]>("tools", workspaceId),
      catalogRequest<ProductList>("products?page=1&page_size=100", workspaceId),
    ]).then(([availableTools, result]) => {
      if (!active) return;
      setTools(availableTools);
      setProducts(result.items);
      if (initialProductId && result.items.some((item) => String(item.id) === initialProductId)) setProductId(initialProductId);
      else if (!productId && result.items[0]) setProductId(String(result.items[0].id));
    }).catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : "页面加载失败"); });
    return () => { active = false; };
  // The initial URL product is a default; keep the user's later selection intact.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, initialProductId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadTasks(); }, 0);
    const poll = window.setInterval(() => { void loadTasks(); }, 5000);
    return () => { window.clearTimeout(timer); window.clearInterval(poll); };
  }, [loadTasks]);

  async function create() {
    if (!productId) { setError("请先选择商品"); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      await agentRequest(`products/${productId}/tasks`, workspaceId, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, requested_tools: tools.filter((tool) => !tool.protected).map((tool) => tool.name), require_approval: true }) });
      await loadTasks();
      setNotice("任务已提交，执行进度会自动刷新。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "创建失败"); }
    finally { setBusy(false); }
  }

  async function decide(task: AgentTask, approvalId: number, result: "approved" | "rejected") {
    setBusy(true); setError("");
    try {
      await agentRequest(`tasks/${task.id}/approvals/${approvalId}`, workspaceId, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result, note: "人工处理" }) });
      await loadTasks();
      setNotice(result === "approved" ? "已批准，任务继续执行。" : "已驳回该步骤。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "审批失败"); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">AGENT CENTER</p><h1>Agent 运营中心</h1><p>为商品创建受控运营任务，查看执行步骤，并处理需要人工确认的动作。</p></div><span className="muted-tag">工作空间隔离 · 操作留痕</span></div>
    {error && <p className="notice error" role="alert">{error}</p>}{notice && <p className="notice success" role="status">{notice}</p>}
    <section className="panel agent-create"><div className="section-heading"><div><p className="eyebrow">NEW TASK</p><h2>创建运营任务</h2><p className="subtle">任务会保存每一步的输入、输出和恢复 checkpoint。</p></div><button className="button primary" disabled={busy || !productId || !form.name.trim() || !form.goal.trim()} onClick={() => void create()}>{busy ? "处理中…" : "创建并运行"}</button></div>
      <div className="form-grid"><div className="agent-product-field"><label htmlFor="agent-product-search">关联商品</label><div className="agent-product-picker"><span className="agent-search-icon" aria-hidden="true">⌕</span><input id="agent-product-search" role="combobox" aria-autocomplete="list" aria-expanded={productPickerOpen} aria-controls="agent-product-options" aria-label="搜索并选择商品" placeholder="搜索商品名称或编号" value={productPickerOpen ? productSearch : selectedProduct ? `${selectedProduct.name} · #${selectedProduct.id}` : productSearch} onFocus={() => { setProductPickerOpen(true); setProductSearch(""); }} onBlur={() => window.setTimeout(() => setProductPickerOpen(false), 120)} onChange={(event) => { setProductPickerOpen(true); setProductSearch(event.target.value); }} onKeyDown={(event) => { if (event.key === "Escape") { setProductPickerOpen(false); setProductSearch(""); } if (event.key === "Enter" && visibleProducts[0]) { event.preventDefault(); setProductId(String(visibleProducts[0].id)); setProductPickerOpen(false); setProductSearch(""); } }} /><span className={`agent-picker-chevron ${productPickerOpen ? "open" : ""}`} aria-hidden="true">⌄</span>{productPickerOpen && <div className="agent-product-options" id="agent-product-options" role="listbox" aria-label="工作区商品">{visibleProducts.length ? visibleProducts.map((product) => <button type="button" role="option" aria-selected={String(product.id) === productId} className={`agent-product-option ${String(product.id) === productId ? "selected" : ""}`} key={product.id} onMouseDown={(event) => event.preventDefault()} onClick={() => { setProductId(String(product.id)); setProductPickerOpen(false); setProductSearch(""); setNotice(""); }}><span className="agent-product-avatar">{product.name.slice(0, 1)}</span><span className="agent-product-copy"><strong>{product.name}</strong><small>{product.category || "未分类"} · 商品 #{product.id}</small></span>{String(product.id) === productId && <span className="agent-product-check">✓</span>}</button>) : <p className="agent-product-empty">没有找到匹配商品</p>}</div>}</div></div><label>任务名称<input value={form.name} maxLength={120} onChange={(event) => setForm({ ...form, name: event.target.value })}/></label><label className="wide">执行目标<textarea value={form.goal} maxLength={2000} onChange={(event) => setForm({ ...form, goal: event.target.value })}/></label></div>
      {!products.length && <p className="subtle">当前工作区还没有商品。先在商品工作台完成建档，再创建 Agent 任务。</p>}
    </section>
    <section className="panel"><div className="section-heading"><div><p className="eyebrow">CONTROLLED TOOLS</p><h2>可用工具</h2><p className="subtle">外部投放和扣费能力不会由 Agent 自动执行。</p></div></div><div className="agent-tools">{tools.map((tool) => <span className={`status-badge ${tool.protected ? "warning" : "ok"}`} title={tool.description} key={tool.name}>{tool.label}{tool.protected ? " · 需审批" : ""}</span>)}</div></section>
    <section className="panel"><div className="section-heading"><div><p className="eyebrow">TASK HISTORY</p><h2>运行记录</h2></div><span className="muted-tag">{tasks.length} 项</span></div>{!productId ? <p className="subtle">选择商品后查看该商品的任务记录。</p> : tasks.length === 0 ? <p className="subtle">该商品还没有 Agent 任务。</p> : <div className="agent-task-list">{tasks.map((task) => <article className="agent-task-card" key={task.id}><div className="sku-head"><div><strong>{task.name}</strong><p>{task.goal}</p></div><span className={`status-badge ${task.status === "failed" ? "warning" : "ok"}`}>{task.status}</span></div>{task.error_message && <p className="notice error">{task.error_message}</p>}<small>步骤 {task.current_step} · checkpoint v{task.checkpoint_version}</small>{task.approvals.filter((approval) => approval.status === "pending").map((approval) => <div className="section-actions" key={approval.id}><span className="muted-tag">等待人工审批</span><button className="button primary" disabled={busy} onClick={() => void decide(task, approval.id, "approved")}>批准继续</button><button className="button secondary" disabled={busy} onClick={() => void decide(task, approval.id, "rejected")}>拒绝</button></div>)}<details><summary>查看执行步骤</summary>{task.steps.map((step) => <div className="agent-step" key={step.id}><strong>{step.step_no}. {step.tool_name}</strong><span className="status-badge">{step.status}</span><pre>{JSON.stringify(step.output_summary, null, 2)}</pre></div>)}</details></article>)}</div>}</section>
  </>;
}

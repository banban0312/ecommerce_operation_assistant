"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { catalogRequest, type Competitor, type Movement, type Product, type ProductList, type Sku, type Store } from "@/lib/catalog";
import { ContentWorkbench } from "@/components/content-workbench";
import { MediaWorkbench } from "@/components/media-workbench";
import { CampaignWorkbench } from "@/components/campaign-workbench";
import { ReviewWorkbench } from "@/components/review-workbench";

export function ProductWorkbench({ productId, workspaceId }: { productId: number; workspaceId: number }) {
  const router = useRouter();
  const [product, setProduct] = useState<Product | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [skus, setSkus] = useState<Sku[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editProduct, setEditProduct] = useState(false);
  const [editSku, setEditSku] = useState<number | null>(null);
  const [adjustSku, setAdjustSku] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextProduct, nextStores, nextProducts, nextSkus, nextMovements, nextCompetitors] = await Promise.all([
        catalogRequest<Product>(`products/${productId}`, workspaceId),
        catalogRequest<Store[]>("stores", workspaceId),
        catalogRequest<ProductList>("products?page_size=100", workspaceId),
        catalogRequest<Sku[]>(`products/${productId}/skus`, workspaceId),
        catalogRequest<Movement[]>(`products/${productId}/inventory-movements`, workspaceId),
        catalogRequest<Competitor[]>(`products/${productId}/competitors`, workspaceId),
      ]);
      setProduct(nextProduct); setStores(nextStores); setAllProducts(nextProducts.items); setSkus(nextSkus); setMovements(nextMovements); setCompetitors(nextCompetitors); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "商品加载失败"); }
  }, [productId, workspaceId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>, path: string, method: "POST" | "PATCH", close?: () => void) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const body: Record<string, unknown> = {};
    values.forEach((value, key) => { body[key] = value; });
    if (path === `products/${productId}` && values.get("cost") === "") body.cost = null;
    if (path.endsWith("/skus")) {
      body.stock = Number(values.get("stock"));
      body.warning_threshold = Number(values.get("warning_threshold"));
    }
    if (path.endsWith("/inventory")) body.quantity = Number(values.get("quantity"));
    if (path.endsWith("/competitors")) {
      // 每行一个“参数: 值”，保存为结构化字段供后续竞品分析复用。
      const attributes: Record<string, string> = {};
      String(values.get("attributes") ?? "").split("\n").forEach((line) => {
        const separator = line.indexOf(":");
        if (separator > 0) attributes[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
      });
      body.attributes = attributes;
    }
    setBusy(true);
    try {
      await catalogRequest(path, workspaceId, { method, body: JSON.stringify(body) });
      form.reset(); close?.(); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setBusy(false); }
  }

  async function removeCompetitor(id: number) {
    if (!window.confirm("确定删除这条竞品资料吗？")) return;
    setBusy(true);
    try { await catalogRequest(`products/${productId}/competitors/${id}`, workspaceId, { method: "DELETE" }); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); }
    finally { setBusy(false); }
  }

  if (!product) return <div className="panel">{error ? <p className="notice error">{error}</p> : "正在加载商品…"}</div>;
  const store = stores.find((item) => item.id === product.store_id);
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">PRODUCT WORKSPACE</p><h1>{product.name}</h1><p>{store?.name ?? "店铺"} · {store?.platform ?? "平台"} · {product.category || "未分类"}</p></div><Link className="button secondary" href="/products">返回商品工作台</Link></div>
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="context-bar"><label>当前商品 <select value={productId} onChange={(event) => router.push(`/products/${event.target.value}`)}>{allProducts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><span>商品 ID：{product.id}</span><span>SKU：{skus.length}</span><span>竞品：{competitors.length}</span></div>
      <nav className="section-nav" aria-label="商品工作台分区"><a href="#profile">商品档案</a><a href="#inventory">SKU 与库存</a><a href="#competitors">竞品对标</a><a href="#ai-content">智能诊断与创意</a><Link href={`/agent?product_id=${productId}`}>Agent 任务</Link><span>投放复盘 · 待开放</span></nav>

      <section className="panel" id="profile">
        <div className="section-heading"><div><p className="eyebrow">PRODUCT PROFILE</p><h2>商品档案</h2></div><button className="button secondary" onClick={() => setEditProduct(!editProduct)}>编辑档案</button></div>
        {editProduct ? <form className="inline-form" onSubmit={(event) => submit(event, `products/${productId}`, "PATCH", () => setEditProduct(false))}><label>商品名称<input name="name" defaultValue={product.name} required maxLength={200} /></label><label>品类<input name="category" defaultValue={product.category} maxLength={120} /></label><label>平台商品编号<input name="platform_item_code" defaultValue={product.platform_item_code} maxLength={100} /></label><label>成本（元）<input name="cost" type="number" min="0" step="0.01" defaultValue={product.cost ?? ""} /></label><label>目标人群<input name="target_audience" defaultValue={product.target_audience} maxLength={500} /></label><label>核心卖点<textarea name="selling_points" defaultValue={product.selling_points} maxLength={5000} /></label><label>基础说明<textarea name="description" defaultValue={product.description} maxLength={5000} /></label><button className="button primary" disabled={busy}>保存档案</button></form> : <div className="profile-grid"><div><small>所属店铺</small><strong>{store?.name ?? "店铺"}</strong></div><div><small>平台</small><strong>{store?.platform ?? "—"}</strong></div><div><small>平台商品编号</small><strong>{product.platform_item_code || "待完善"}</strong></div><div><small>品类</small><strong>{product.category || "未分类"}</strong></div><div><small>成本</small><strong>{product.cost === null ? "待完善" : `¥${product.cost}`}</strong></div><div><small>售价区间</small><strong>{skus.length ? `¥${Math.min(...skus.map((sku) => Number(sku.price)))}–${Math.max(...skus.map((sku) => Number(sku.price)))}` : "未定价"}</strong></div><div><small>目标人群</small><p>{product.target_audience || "待完善"}</p></div><div><small>核心卖点</small><p>{product.selling_points || "待完善"}</p></div><div><small>商品说明</small><p>{product.description || "尚未填写"}</p></div></div>}
      </section>

      <section className="panel" id="inventory">
        <div className="section-heading"><div><p className="eyebrow">SKU & INVENTORY</p><h2>规格与库存</h2></div><span className="muted-tag">{skus.length} 个 SKU</span></div>
        <form className="inline-form" onSubmit={(event) => submit(event, `products/${productId}/skus`, "POST")}><label>SKU 编号<input name="sku_code" required maxLength={100} placeholder="WHITE-M" /></label><label>规格<input name="specification" required maxLength={200} placeholder="白色 M" /></label><label>价格（元）<input name="price" type="number" min="0" step="0.01" required /></label><label>初始库存<input name="stock" type="number" min="0" defaultValue="0" required /></label><label>预警阈值<input name="warning_threshold" type="number" min="0" defaultValue="5" required /></label><button className="button primary" disabled={busy}>添加 SKU</button></form>
        {skus.length ? <div className="sku-grid">{skus.map((sku) => <div className="sku-card" key={sku.id}><div className="sku-head"><strong>{sku.specification}</strong><span className={sku.stock < sku.warning_threshold ? "warn-text" : ""}>{sku.stock < sku.warning_threshold ? "库存预警" : "库存正常"}</span></div><small>{sku.sku_code}</small><div className="sku-numbers"><span>¥{sku.price}</span><span>库存 {sku.stock}</span><span>阈值 {sku.warning_threshold}</span></div><div className="section-actions"><button className="button secondary" onClick={() => { setEditSku(editSku === sku.id ? null : sku.id); setAdjustSku(null); }}>编辑规格</button><button className="button secondary" onClick={() => { setAdjustSku(adjustSku === sku.id ? null : sku.id); setEditSku(null); }}>调整库存</button></div>{editSku === sku.id && <form className="mini-form" onSubmit={(event) => submit(event, `products/${productId}/skus/${sku.id}`, "PATCH", () => setEditSku(null))}><label>规格<input name="specification" defaultValue={sku.specification} required /></label><label>价格<input name="price" type="number" min="0" step="0.01" defaultValue={sku.price} required /></label><label>阈值<input name="warning_threshold" type="number" min="0" defaultValue={sku.warning_threshold} required /></label><button className="button primary" disabled={busy}>保存</button></form>}{adjustSku === sku.id && <form className="mini-form" onSubmit={(event) => submit(event, `products/${productId}/skus/${sku.id}/inventory`, "POST", () => setAdjustSku(null))}><label>调整后库存<input name="quantity" type="number" min="0" defaultValue={sku.stock} required /></label><label>原因<input name="reason" required maxLength={200} placeholder="盘点调整" /></label><button className="button primary" disabled={busy}>记录变更</button></form>}</div>)}</div> : <p className="subtle">暂无 SKU，请添加不同规格。</p>}
        <h3 className="subheading">库存流水</h3>{movements.length ? <div className="list-table"><div className="table-head"><span>SKU</span><span>变更量</span><span>调整后</span><span>原因 / 时间</span></div>{movements.map((movement) => <div className="table-row" key={movement.id}><span>{skus.find((sku) => sku.id === movement.sku_id)?.sku_code ?? `SKU ${movement.sku_id}`}</span><strong>{movement.delta > 0 ? `+${movement.delta}` : movement.delta}</strong><span>{movement.quantity_after}</span><span>{movement.reason}<small>{new Date(movement.created_at).toLocaleString("zh-CN")}</small></span></div>)}</div> : <p className="subtle">还没有库存变更。</p>}
      </section>

      <section className="panel" id="competitors">
        <div className="section-heading"><div><p className="eyebrow">COMPETITOR BENCHMARK</p><h2>竞品对标</h2></div><span className="muted-tag">人工录入 · 链接解析后续开放</span></div>
        <form className="inline-form" onSubmit={(event) => submit(event, `products/${productId}/competitors`, "POST")}><label>竞品名称<input name="name" required maxLength={200} /></label><label>价格（元）<input name="price" type="number" min="0" step="0.01" required /></label><label>关键参数（每行 参数: 值）<textarea name="attributes" placeholder={"面料: 锦纶\n防晒指数: UPF50+"} /></label><label>公开链接（可选）<input name="source_url" type="url" maxLength={1000} /></label><button className="button primary" disabled={busy}>保存竞品</button></form>
        {competitors.length ? <div className="competitor-grid">{competitors.map((item) => <article className="competitor-card" key={item.id}><div className="sku-head"><h3>{item.name}</h3><strong>¥{item.price}</strong></div><dl>{Object.entries(item.attributes).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>{item.source_url && <><span className="muted-tag">{item.source_status === "parsed" ? "来源已解析" : "待人工补录"}{item.source_fetched_at ? ` · ${new Date(item.source_fetched_at).toLocaleString("zh-CN")}` : ""}</span><a href={item.source_url} target="_blank" rel="noreferrer">查看来源 ↗</a></>}<button className="button secondary" disabled={busy} onClick={() => removeCompetitor(item.id)}>删除</button></article>)}</div> : <p className="subtle">暂无竞品资料。</p>}
      </section>
      <ContentWorkbench productId={productId} workspaceId={workspaceId} />
      <MediaWorkbench productId={productId} workspaceId={workspaceId} />
      <CampaignWorkbench productId={productId} workspaceId={workspaceId} />
      <ReviewWorkbench productId={productId} workspaceId={workspaceId} />
      <section className="panel"><div className="section-heading"><div><p className="eyebrow">NEXT STEPS</p><h2>后续环节</h2></div></div><div className="future-grid"><span>投放建议与经营复盘 · 后续阶段</span></div></section>
    </>
  );
}

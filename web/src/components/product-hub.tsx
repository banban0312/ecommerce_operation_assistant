"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { catalogRequest, priceRange, type ProductList, type Store, type Summary } from "@/lib/catalog";

type View = "all" | "recent" | "warning" | "incomplete";
const empty: ProductList = { items: [], total: 0, page: 1, page_size: 20 };

export function ProductHub({ workspaceId, initialStoreId }: { workspaceId: number; initialStoreId: string }) {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductList>(empty);
  const [summary, setSummary] = useState<Summary>({ store_count: 0, product_count: 0, warning_count: 0, warnings: [] });
  const [incompleteCount, setIncompleteCount] = useState(0);
  const [view, setView] = useState<View>("all");
  const [query, setQuery] = useState("");
  const [storeId, setStoreId] = useState(initialStoreId);
  const [platform, setPlatform] = useState("");
  const [stockStatus, setStockStatus] = useState("");
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (query.trim()) params.set("q", query.trim());
      if (storeId) params.set("store_id", storeId);
      if (platform) params.set("platform", platform);
      if (stockStatus || view === "warning") params.set("stock_status", view === "warning" ? "warning" : stockStatus);
      if (view === "incomplete") params.set("profile_incomplete", "true");
      if (view === "recent") params.set("sort", "updated");
      const [nextStores, nextProducts, nextSummary, incomplete] = await Promise.all([
        catalogRequest<Store[]>("stores", workspaceId),
        catalogRequest<ProductList>(`products?${params}`, workspaceId),
        catalogRequest<Summary>("dashboard", workspaceId),
        catalogRequest<ProductList>("products?page_size=1&profile_incomplete=true", workspaceId),
      ]);
      setStores(nextStores); setProducts(nextProducts); setSummary(nextSummary); setIncompleteCount(incomplete.total); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "商品工作台加载失败"); }
  }, [workspaceId, page, query, storeId, platform, stockStatus, view]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    try {
      await catalogRequest("products", workspaceId, { method: "POST", body: JSON.stringify({
        store_id: Number(values.get("store_id")), name: values.get("name"), category: values.get("category"),
        platform_item_code: values.get("platform_item_code"), description: values.get("description"),
      }) });
      form.reset(); setShowForm(false); setView("all"); setPage(1); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "创建商品失败"); }
    finally { setBusy(false); }
  }

  const changeView = (next: View) => { setView(next); setPage(1); };
  const platforms = Array.from(new Set(stores.map((store) => store.platform)));
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">PRODUCT WORKSPACE</p><h1>商品工作台</h1><p>检索商品、查看库存风险和档案状态，再进入单品处理。</p></div><div className="section-actions"><button className="button secondary" disabled title="将在导入中心阶段开放">批量导入 · 待开放</button><button className="button primary" disabled={!stores.length} onClick={() => setShowForm(!showForm)}>＋ 新建商品</button></div></div>
      {error && <p className="notice error" role="alert">{error}</p>}
      <section className="metric-grid" aria-label="商品概览">
        <div className="metric-card"><span>商品总数</span><strong>{summary.product_count}</strong><small>当前工作区</small></div>
        <div className="metric-card"><span>店铺数</span><strong>{summary.store_count}</strong><small>已接入店铺</small></div>
        <div className="metric-card warning"><span>库存预警</span><strong>{summary.warning_count}</strong><small>低于阈值的 SKU</small></div>
        <div className="metric-card"><span>档案待完善</span><strong>{incompleteCount}</strong><small>缺少关键商品信息</small></div>
      </section>
      {showForm && <form className="inline-form" onSubmit={createProduct}><label>所属店铺<select name="store_id" required defaultValue=""><option value="" disabled>选择店铺</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></label><label>商品名称<input name="name" required maxLength={200} /></label><label>品类<input name="category" maxLength={120} /></label><label>平台商品编号<input name="platform_item_code" maxLength={100} /></label><label>商品说明<input name="description" maxLength={5000} /></label><button className="button primary" disabled={busy}>保存商品</button></form>}
      <div className="hub-layout">
        <section className="panel hub-main" aria-label="商品池">
          <div className="hub-tabs" role="tablist" aria-label="商品视图">
            {([ ["all", "全部商品"], ["recent", "最近更新"], ["warning", "库存预警"], ["incomplete", "档案待完善"] ] as const).map(([key, label]) => <button role="tab" aria-selected={view === key} className={view === key ? "selected" : ""} key={key} onClick={() => changeView(key)}>{label}</button>)}
          </div>
          <div className="filter-row"><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索商品名称 / SKU" aria-label="搜索商品名称或 SKU" /><select value={storeId} onChange={(event) => { setStoreId(event.target.value); setPage(1); }} aria-label="按店铺筛选"><option value="">全部店铺</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select><select value={platform} onChange={(event) => { setPlatform(event.target.value); setPage(1); }} aria-label="按平台筛选"><option value="">全部平台</option>{platforms.map((item) => <option key={item}>{item}</option>)}</select><select value={stockStatus} onChange={(event) => { setStockStatus(event.target.value); setPage(1); }} aria-label="按库存状态筛选" disabled={view === "warning"}><option value="">全部库存状态</option><option value="normal">正常</option><option value="warning">预警</option><option value="no_sku">无 SKU</option></select></div>
          {products.items.length ? <div className="list-table hub-table"><div className="table-head"><span>商品 / 平台编号</span><span>店铺 / 平台</span><span>SKU</span><span>售价</span><span>库存状态</span><span>操作</span></div>{products.items.map((product) => { const store = stores.find((item) => item.id === product.store_id); return <div className="table-row" key={product.id}><span><strong>{product.name}</strong><small>{product.platform_item_code || "未填写平台编号"}</small></span><span>{store?.name ?? "店铺"}<small>{store?.platform ?? "—"}</small></span><span>{product.sku_count}</span><span>{priceRange(product)}</span><span className={product.has_stock_warning ? "warn-text" : ""}>{product.sku_count === 0 ? "无 SKU" : product.has_stock_warning ? "库存预警" : "正常"}</span><Link href={`/products/${product.id}`}>进入单品 →</Link></div>; })}</div> : <p className="subtle">当前条件下没有商品。{!stores.length ? "请先在运营大盘创建店铺。" : ""}</p>}
          <div className="pager"><span>共 {products.total} 件商品</span><div><button className="button secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><span>第 {page} 页</span><button className="button secondary" disabled={page * 20 >= products.total} onClick={() => setPage(page + 1)}>下一页</button></div></div>
        </section>
        <aside className="hub-rail"><section className="panel"><h2>最近工作</h2><p className="subtle">按最近更新查看商品档案。</p><button className="text-action" onClick={() => changeView("recent")}>查看最近更新 →</button></section><section className="panel"><h2>需要关注</h2><p className="subtle">{summary.warning_count} 个 SKU 库存预警，{incompleteCount} 件商品档案待完善。</p><button className="text-action" onClick={() => changeView("warning")}>处理库存预警 →</button></section></aside>
      </div>
    </>
  );
}

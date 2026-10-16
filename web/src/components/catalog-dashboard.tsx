"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { catalogRequest, priceRange, type ProductList, type Store, type Summary } from "@/lib/catalog";

export function CatalogDashboard({ workspaceId }: { workspaceId: number }) {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductList>({ items: [], total: 0, page: 1, page_size: 20 });
  const [summary, setSummary] = useState<Summary>({ store_count: 0, product_count: 0, warning_count: 0, warnings: [] });
  const [storeFilter, setStoreFilter] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [showStoreForm, setShowStoreForm] = useState(false);
  const [showProductForm, setShowProductForm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (storeFilter) params.set("store_id", storeFilter);
      if (query.trim()) params.set("q", query.trim());
      const [nextStores, nextProducts, nextSummary] = await Promise.all([
        catalogRequest<Store[]>("stores", workspaceId),
        catalogRequest<ProductList>(`products?${params}`, workspaceId),
        catalogRequest<Summary>("dashboard", workspaceId),
      ]);
      setStores(nextStores);
      setProducts(nextProducts);
      setSummary(nextSummary);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载失败");
    }
  }, [workspaceId, storeFilter, query, page]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createStore(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    try {
      await catalogRequest("stores", workspaceId, { method: "POST", body: JSON.stringify({ name: values.get("name"), platform: values.get("platform") }) });
      form.reset(); setShowStoreForm(false); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "创建店铺失败"); }
    finally { setBusy(false); }
  }

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    try {
      await catalogRequest("products", workspaceId, { method: "POST", body: JSON.stringify({ store_id: Number(values.get("store_id")), name: values.get("name"), category: values.get("category"), description: values.get("description") }) });
      form.reset(); setShowProductForm(false); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "创建商品失败"); }
    finally { setBusy(false); }
  }

  return (
    <>
      {error && <p className="notice error" role="alert">{error}</p>}
      <section className="metric-grid" aria-label="店铺与商品概览">
        <div className="metric-card"><span>店铺总数</span><strong>{summary.store_count}</strong><small>当前工作区</small></div>
        <div className="metric-card"><span>商品总数</span><strong>{summary.product_count}</strong><small>已建档商品</small></div>
        <div className="metric-card warning"><span>库存预警</span><strong>{summary.warning_count}</strong><small>低于 SKU 阈值</small></div>
        <div className="metric-card"><span>当前阶段</span><strong className="metric-text">M2</strong><small>商品与库存建档</small></div>
      </section>

      <section className="panel" id="stores">
        <div className="section-heading"><div><p className="eyebrow">STORES</p><h2>店铺概览</h2></div><button className="button primary" onClick={() => setShowStoreForm(!showStoreForm)}>新建店铺</button></div>
        {showStoreForm && <form className="inline-form" onSubmit={createStore}><label>店铺名称<input name="name" required maxLength={160} placeholder="例如：夏季服饰旗舰店" /></label><label>平台<select name="platform" required><option value="抖音">抖音</option><option value="淘宝">淘宝</option><option value="天猫">天猫</option><option value="京东">京东</option><option value="拼多多">拼多多</option><option value="其他">其他</option></select></label><button className="button primary" disabled={busy}>保存店铺</button></form>}
        {stores.length ? <div className="store-list">{stores.map((store) => <div key={store.id} className={`store-chip ${storeFilter === String(store.id) ? "selected" : ""}`}><button className="store-choice" onClick={() => { setStoreFilter(storeFilter === String(store.id) ? "" : String(store.id)); setPage(1); }}>{store.name}<small>{store.platform} · {store.product_count} 件商品</small></button><Link className="text-action" href={`/products?store_id=${store.id}`}>查看商品 →</Link></div>)}</div> : <p className="subtle">还没有店铺，先创建一个店铺开始商品建档。</p>}
      </section>

      <section className="panel" id="warnings">
        <div className="section-heading"><div><p className="eyebrow">INVENTORY ALERTS</p><h2>库存预警</h2></div><span className="muted-tag">{summary.warning_count} 个 SKU</span></div>
        {summary.warnings.length ? <div className="list-table"><div className="table-head"><span>商品 / SKU</span><span>当前库存</span><span>预警阈值</span><span>操作</span></div>{summary.warnings.map((item) => <div className="table-row" key={item.sku_id}><span>{item.product_name}<small>{item.sku_code}</small></span><strong className="warn-text">{item.stock}</strong><span>{item.warning_threshold}</span><Link href={`/products/${item.product_id}#inventory`}>查看商品 →</Link></div>)}</div> : <p className="subtle">暂无低于阈值的 SKU。</p>}
      </section>

      <section className="panel" id="products">
        <div className="section-heading"><div><p className="eyebrow">PRODUCT WORKSPACE</p><h2>商品列表</h2></div><div className="section-actions"><button className="button secondary" disabled title="将在导入中心阶段开放">批量导入 · 待开放</button><button className="button primary" onClick={() => setShowProductForm(!showProductForm)} disabled={!stores.length}>新建商品</button></div></div>
        {showProductForm && <form className="inline-form" onSubmit={createProduct}><label>所属店铺<select name="store_id" required defaultValue={storeFilter}><option value="" disabled>选择店铺</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select></label><label>商品名称<input name="name" required maxLength={200} placeholder="例如：夏季防晒衣" /></label><label>品类<input name="category" maxLength={120} placeholder="服装" /></label><label>基础说明<input name="description" maxLength={5000} placeholder="商品定位与基础信息" /></label><button className="button primary" disabled={busy}>保存商品</button></form>}
        <div className="filter-row"><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索商品名称 / SKU" aria-label="搜索商品名称或 SKU" /><select value={storeFilter} onChange={(event) => { setStoreFilter(event.target.value); setPage(1); }} aria-label="按店铺筛选"><option value="">全部店铺</option>{stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}</select><Link className="button secondary" href="/products">打开商品工作台 →</Link></div>
        {products.items.length ? <div className="list-table hub-table"><div className="table-head"><span>商品 / 平台编号</span><span>店铺</span><span>SKU</span><span>售价</span><span>库存状态</span><span>操作</span></div>{products.items.map((product) => <div className="table-row" key={product.id}><span><strong>{product.name}</strong><small>{product.platform_item_code || "未填写平台编号"}</small></span><span>{stores.find((store) => store.id === product.store_id)?.name ?? "店铺"}</span><span>{product.sku_count}</span><span>{priceRange(product)}</span><span className={product.has_stock_warning ? "warn-text" : ""}>{product.sku_count === 0 ? "无 SKU" : product.has_stock_warning ? "库存预警" : "正常"}</span><Link href={`/products/${product.id}`}>进入单品 →</Link></div>)}</div> : <p className="subtle">当前条件下没有商品。</p>}
        <div className="pager"><span>共 {products.total} 件商品</span><div><button className="button secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><span>第 {page} 页</span><button className="button secondary" disabled={page * 20 >= products.total} onClick={() => setPage(page + 1)}>下一页</button></div></div>
      </section>
    </>
  );
}

export type Store = { id: number; name: string; platform: string; status: string; product_count: number };
export type Product = { id: number; store_id: number; name: string; category: string; description: string; platform_item_code: string; cost: string | null; target_audience: string; selling_points: string; status: string; updated_at: string };
export type ProductListItem = Product & { sku_count: number; price_min: string | null; price_max: string | null; has_stock_warning: boolean };
export type Sku = { id: number; product_id: number; sku_code: string; specification: string; price: string; stock: number; warning_threshold: number; status: string };
export type Movement = { id: number; sku_id: number; delta: number; quantity_after: number; reason: string; created_at: string };
export type Competitor = { id: number; name: string; price: string; attributes: Record<string, string>; source_url: string | null; source_status: string; source_fetched_at: string | null; source_snapshot: Record<string, unknown> };
export type Summary = { store_count: number; product_count: number; warning_count: number; warnings: { product_id: number; product_name: string; sku_id: number; sku_code: string; stock: number; warning_threshold: number }[] };
export type ProductList = { items: ProductListItem[]; total: number; page: number; page_size: number };
export type Trends = { period_start: string | null; period_end: string | null; stores: Store[]; series: { product_id: number; product_name: string; store_id: number; store_name: string; points: { period_start: string; period_end: string; actual_gmv: string | null; target_gmv: string | null; actual_roi: string | null; actual_conversion_rate: string | null }[] }[] };

// 商品报价属于 SKU；列表只展示规格价格区间，不再把某个 SKU 当作整件商品的售价。
export function priceRange(product: ProductListItem): string {
  if (product.price_min === null) return "未定价";
  return product.price_min === product.price_max ? `¥${product.price_min}` : `¥${product.price_min}–${product.price_max}`;
}

export async function catalogRequest<T>(path: string, workspaceId: number, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/catalog/${path}`, {
    ...init,
    headers: { "X-Workspace-ID": String(workspaceId), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

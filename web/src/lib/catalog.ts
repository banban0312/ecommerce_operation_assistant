export type Store = { id: number; name: string; platform: string; status: string };
export type Product = { id: number; store_id: number; name: string; category: string; description: string; status: string };
export type Sku = { id: number; product_id: number; sku_code: string; specification: string; price: string; stock: number; warning_threshold: number; status: string };
export type Movement = { id: number; sku_id: number; delta: number; quantity_after: number; reason: string; created_at: string };
export type Competitor = { id: number; name: string; price: string; attributes: Record<string, string>; source_url: string | null };
export type Summary = { store_count: number; product_count: number; warning_count: number; warnings: { product_id: number; product_name: string; sku_id: number; sku_code: string; stock: number; warning_threshold: number }[] };
export type ProductList = { items: Product[]; total: number; page: number; page_size: number };

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

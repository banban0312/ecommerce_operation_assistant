export type ContentType = "diagnosis" | "image_idea" | "video_script";
export type ContentItem = { id: number; product_id: number; content_type: ContentType; slot_key: string; version_no: number; revision: number; status: "draft" | "confirmed" | "archived"; source: "model" | "human"; content: Record<string, unknown>; updated_by: number; created_at: string; updated_at: string };
export type ContentBundle = { product_id: number; diagnosis: ContentItem[]; image_ideas: ContentItem[]; video_scripts: ContentItem[] };

export async function contentRequest<T>(path: string, workspaceId: number, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/content/${path}`, { ...init, headers: { "X-Workspace-ID": String(workspaceId), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers }, cache: "no-store" });
  if (!response.ok) { const body = await response.json().catch(() => ({})) as { message?: string }; throw new Error(body.message ?? `请求失败（${response.status}）`); }
  return await response.json() as T;
}

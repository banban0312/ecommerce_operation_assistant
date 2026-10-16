export type Target = "text" | "image" | "video";
export type ServiceConfig = { target: Target; provider: string; model: string; has_api_key: boolean; configured: boolean; key_source: "environment" };
export type TaskRules = { timeout_seconds: number; max_retries: number; max_concurrency: number; image_poll_interval_seconds: number; image_poll_max_attempts: number; video_poll_interval_seconds: number; video_poll_max_attempts: number };
export type PlatformAccount = { store_id: number; store_name: string; platform: string; account_identifier: string; authorization_status: "not_connected" | "placeholder" };
export type SettingsData = { services: ServiceConfig[]; rules: TaskRules; platforms: PlatformAccount[] };
export type ConnectionResult = { target: Target; ok: boolean; code: string; message: string; checked_at: string };
export type ConfigAudit = { id: number; actor_name: string; action: string; resource_type: string; resource_id: string | null; details: Record<string, unknown> | null; created_at: string };

export async function settingsRequest<T>(path: string, workspaceId: number, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/settings/${path}`, {
    ...init,
    headers: { "X-Workspace-ID": String(workspaceId), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? `请求失败（${response.status}）`);
  }
  return await response.json() as T;
}

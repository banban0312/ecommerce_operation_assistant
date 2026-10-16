export type WorkspaceMember = {
  id: number;
  email: string;
  display_name: string;
  role: "operator" | "supervisor" | "admin";
  status: "active" | "disabled";
  last_login_at: string | null;
};

export type CreateMember = {
  email: string;
  display_name: string;
  password: string;
  role: WorkspaceMember["role"];
};

export async function membersRequest<T>(
  workspaceId: number,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/members/workspaces/${workspaceId}/members`, {
    ...init,
    headers: {
      "X-Workspace-ID": String(workspaceId),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { message?: string; detail?: string };
    throw new Error(body.message ?? body.detail ?? `请求失败（${response.status}）`);
  }
  return await response.json() as T;
}

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export type Membership = { workspace_id: number; workspace_name: string; role: string };
export type Identity = {
  id: number;
  display_name: string;
  email: string;
  memberships: Membership[];
};

export async function requireIdentity(): Promise<Identity> {
  const token = (await cookies()).get("eoa_access_token")?.value;
  if (!token) redirect("/login");
  const apiBase = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let response: Response;
  try {
    response = await fetch(new URL("/api/v1/auth/me", apiBase), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    redirect("/login");
  }
  if (!response.ok) redirect("/login");
  return (await response.json()) as Identity;
}

import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context) {
  const token = request.cookies.get("eoa_access_token")?.value;
  if (!token) return NextResponse.json({ message: "请先登录" }, { status: 401 });
  const { path } = await context.params;
  if (!path.length || path.some((part) => !/^[a-z0-9-]+$/i.test(part))) return NextResponse.json({ message: "路径不合法" }, { status: 400 });
  const workspaceId = request.headers.get("x-workspace-id");
  if (!workspaceId || !/^[1-9]\d*$/.test(workspaceId)) return NextResponse.json({ message: "请选择工作空间" }, { status: 400 });
  const target = new URL(`/api/v1/content/${path.join("/")}`, process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000");
  const headers: HeadersInit = { Authorization: `Bearer ${token}`, "X-Workspace-ID": workspaceId };
  let body: string | undefined;
  if (request.method !== "GET") { headers["Content-Type"] = "application/json"; body = await request.text(); }
  try {
    const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(40000) });
    return new NextResponse(await upstream.text(), { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } });
  } catch { return NextResponse.json({ message: "暂时无法连接内容服务" }, { status: 503 }); }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;

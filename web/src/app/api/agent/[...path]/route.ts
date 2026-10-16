import { NextRequest, NextResponse } from "next/server";
type Context = { params: Promise<{ path: string[] }> };
async function forward(request: NextRequest, context: Context) {
  const token = request.cookies.get("eoa_access_token")?.value;
  if (!token) return NextResponse.json({ message: "请先登录" }, { status: 401 });
  const { path } = await context.params;
  const workspaceId = request.headers.get("x-workspace-id");
  if (!path.length || !workspaceId) return NextResponse.json({ message: "请求参数不完整" }, { status: 400 });
  const target = new URL(`/api/v1/agent/${path.join("/")}`, process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000");
  const headers: HeadersInit = { Authorization: `Bearer ${token}`, "X-Workspace-ID": workspaceId };
  let body: BodyInit | undefined;
  if (request.method !== "GET") { body = await request.arrayBuffer(); const type = request.headers.get("content-type"); if (type) headers["Content-Type"] = type; }
  try { const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(40000) }); return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } }); } catch { return NextResponse.json({ message: "暂时无法连接 Agent 服务" }, { status: 503 }); }
}
export const GET = forward; export const POST = forward;

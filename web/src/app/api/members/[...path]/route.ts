import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ path?: string[] }> };

async function forward(request: NextRequest, context: Context) {
  const token = request.cookies.get("eoa_access_token")?.value;
  if (!token) return NextResponse.json({ message: "请先登录" }, { status: 401 });

  const { path = [] } = await context.params;
  if (
    path.length !== 3 ||
    path[0] !== "workspaces" ||
    !/^[1-9]\d*$/.test(path[1]) ||
    path[2] !== "members"
  ) {
    return NextResponse.json({ message: "成员管理路径不合法" }, { status: 400 });
  }

  const workspaceId = request.headers.get("x-workspace-id");
  if (workspaceId !== path[1]) {
    return NextResponse.json({ message: "工作空间信息不匹配" }, { status: 400 });
  }

  const target = new URL(
    `/api/v1/auth/${path.join("/")}`,
    process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000",
  );
  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
    "X-Workspace-ID": workspaceId,
  };
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body) headers["Content-Type"] = "application/json";

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ message: "暂时无法连接成员管理服务" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;

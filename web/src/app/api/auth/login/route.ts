import { NextRequest, NextResponse } from "next/server";

type LoginResult = {
  access_token: string;
  expires_in: number;
  user: { id: number; email: string; display_name: string; memberships: unknown[] };
};

export async function POST(request: NextRequest) {
  let credentials: { email?: string; password?: string };
  try {
    credentials = await request.json();
  } catch {
    return NextResponse.json({ message: "请填写邮箱和密码。" }, { status: 400 });
  }

  const apiUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let response: Response;
  try {
    response = await fetch(new URL("/api/v1/auth/login", apiUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    return NextResponse.json({ message: "暂时无法连接登录服务，请稍后重试。" }, { status: 503 });
  }

  if (!response.ok) {
    return NextResponse.json(
      { message: response.status === 401 ? "邮箱或密码错误。" : "该账号暂时无法登录。" },
      { status: response.status },
    );
  }

  const result = (await response.json()) as LoginResult;
  const reply = NextResponse.json({ user: result.user });
  reply.cookies.set("eoa_access_token", result.access_token, {
    httpOnly: true,
    sameSite: "lax",
    // Docker 本地也是 production 构建；只有当前连接实际使用 HTTPS 时才设置 Secure。
    secure:
      request.nextUrl.protocol === "https:" ||
      request.headers.get("x-forwarded-proto")?.split(",")[0].trim() === "https",
    path: "/",
    maxAge: result.expires_in,
  });
  return reply;
}

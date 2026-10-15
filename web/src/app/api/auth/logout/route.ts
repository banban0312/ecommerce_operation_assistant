import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  // 使用相对跳转地址，避免容器内的 0.0.0.0 被作为浏览器访问地址。
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login" } });
  response.cookies.set("eoa_access_token", "", {
    httpOnly: true,
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: 0,
  });
  return response;
}

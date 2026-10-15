import { fetchApiHealth } from "@/lib/health";

export const dynamic = "force-dynamic";

export async function GET() {
  // 浏览器只访问同源地址，由 Next.js 服务端转发到容器内部的 API。
  try {
    const report = await fetchApiHealth();
    return Response.json(report, {
      status: report.status === "ok" ? 200 : 503,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { service: "api", status: "degraded", checks: {}, message: "暂时无法连接 API 服务，请稍后重试。" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

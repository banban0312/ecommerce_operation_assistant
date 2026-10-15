// 容器存活探针只检查 Web 进程，不依赖后端 API 或数据库。
export function GET() {
  return Response.json({ service: "web", status: "ok" }, {
    headers: { "Cache-Control": "no-store" },
  });
}

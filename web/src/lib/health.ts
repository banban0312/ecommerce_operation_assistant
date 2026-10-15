export type HealthReport = {
  service: string;
  status: "ok" | "degraded";
  checks: Record<string, { status: "ok" | "unavailable" }>;
};

export async function fetchApiHealth(): Promise<HealthReport> {
  // 此函数在 Next.js 服务端运行，API_INTERNAL_URL 只需在容器网络内可访问。
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL("/health/ready", baseUrl), {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });
  if (response.status !== 200 && response.status !== 503) {
    throw new Error("Unexpected API health response");
  }
  const result = (await response.json()) as HealthReport;
  // 展示或转发响应前先校验最小数据结构，避免错误格式进入页面。
  if ((result.status !== "ok" && result.status !== "degraded") || !result.checks) {
    throw new Error("Invalid API health response");
  }
  return result;
}

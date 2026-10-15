export type HealthReport = {
  service: string;
  status: "ok" | "degraded";
  checks: Record<string, { status: "ok" | "unavailable" }>;
};

export async function fetchApiHealth(): Promise<HealthReport> {
  // This runs on the Next.js server, so API_INTERNAL_URL stays inside the container network.
  const baseUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL("/health/ready", baseUrl), {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });
  if (response.status !== 200 && response.status !== 503) {
    throw new Error("Unexpected API health response");
  }
  const result = (await response.json()) as HealthReport;
  // Validate the minimal response contract before rendering it or forwarding it to the browser.
  if ((result.status !== "ok" && result.status !== "degraded") || !result.checks) {
    throw new Error("Invalid API health response");
  }
  return result;
}

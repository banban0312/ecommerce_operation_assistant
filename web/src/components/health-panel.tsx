"use client";

import { useCallback, useState } from "react";
import type { HealthReport } from "@/lib/health";

const services = [
  { key: "api", name: "API 服务", description: "工作台与数据服务的连接" },
  { key: "database", name: "业务数据库", description: "MySQL 持久化连接" },
  { key: "redis", name: "任务队列", description: "Redis 消息服务连接" },
  { key: "storage", name: "素材存储", description: "本地素材卷读写检查" },
];

export function HealthPanel({ initialReport }: { initialReport: HealthReport }) {
  // Keep the server-rendered report as the initial UI state to avoid a loading flash on page load.
  const [report, setReport] = useState<HealthReport>(initialReport);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    // Refresh through the same-origin Next route, which safely proxies the internal API address.
    try {
      const response = await fetch("/api/health", { cache: "no-store", signal });
      const data = (await response.json()) as HealthReport;
      if (!signal?.aborted) setReport(data);
    } catch {
      if (!signal?.aborted) setReport({ service: "api", status: "degraded", checks: {} });
    } finally {
      if (!signal?.aborted) {
        setChecking(false);
        setCheckedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      }
    }
  }, []);

  return (
    <section className="panel" aria-labelledby="health-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">基础服务</p>
          <h2 id="health-title">工作台连接状态</h2>
        </div>
        <button className="button secondary" disabled={checking} onClick={() => { setChecking(true); void refresh(); }}>
          {checking ? "正在检查…" : "重新检查"}
        </button>
      </div>
      <div className="service-grid" aria-live="polite" aria-busy={checking}>
        {services.map((service) => {
          const available = service.key === "api"
            ? report !== null && Object.keys(report.checks).length > 0
            : report?.checks[service.key]?.status === "ok";
          const state = checking ? "checking" : available ? "ok" : "unavailable";
          return (
            <div className="service-card" key={service.key}>
              <span className={`status-badge ${state}`}>
                <span className="status-dot" />
                {checking ? "检查中" : available ? "已连接" : "连接异常"}
              </span>
              <h3>{service.name}</h3>
              <p>{service.description}</p>
            </div>
          );
        })}
      </div>
      <p className="health-note" role="status">
        {!checking && report?.status === "degraded"
          ? "部分服务暂不可用，请检查容器状态后重新连接。"
          : "连接状态来自实际服务检查。Worker 执行链路可通过本地验收脚本验证。"}
        {checkedAt && <span>最近检查 {checkedAt}</span>}
      </p>
    </section>
  );
}

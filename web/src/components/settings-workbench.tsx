"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { settingsRequest, type ConfigAudit, type ConnectionResult, type PlatformAccount, type ServiceConfig, type SettingsData, type Target, type TaskRules } from "@/lib/settings";
import { UiSelect } from "@/components/ui-select";

const labels: Record<Target, string> = { text: "文本模型", image: "图片生成", video: "视频生成" };
const auditLabels: Record<string, string> = {
  "settings.service_updated": "修改服务参数",
  "settings.rules_updated": "修改任务规则",
  "settings.platform_placeholder_updated": "修改平台占位",
  "settings.connection_checked": "执行连接检查",
};

function ServiceCard({ service, workspaceId, refresh }: { service: ServiceConfig; workspaceId: number; refresh: () => Promise<void> }) {
  const [provider, setProvider] = useState(service.provider);
  const [model, setModel] = useState(service.model);
  const [endpoint, setEndpoint] = useState(service.endpoint_url);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [result, setResult] = useState<ConnectionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");


  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      await settingsRequest(`services/${service.target}`, workspaceId, { method: "PATCH", body: JSON.stringify({ provider, model, endpoint_url: endpoint, api_key: apiKey || null, clear_api_key: clearKey }) });
      setApiKey(""); setClearKey(false);
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setBusy(false); }
  }

  async function check() {
    setBusy(true); setError(""); setResult(null);
    try {
      setResult(await settingsRequest<ConnectionResult>(`services/${service.target}/check`, workspaceId, { method: "POST" }));
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "检查失败"); }
    finally { setBusy(false); }
  }

  return <form className="service-card-settings" onSubmit={save}>
    <div className="service-card-heading"><h2>{labels[service.target]}</h2><span className={`config-status ${service.configured ? "ready" : ""}`}>{service.configured ? "已配置" : "待配置"}</span></div>
    <label>服务供应商{service.target === "video" ? <UiSelect value={provider} onChange={setProvider} ariaLabel="服务供应商" options={[{ value: "none", label: "待选择" }, { value: "jimeng", label: "即梦" }, { value: "dashscope", label: "DashScope" }]} /> : <input value="OpenAI 兼容接口" readOnly />}</label>
    <label>服务地址<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} maxLength={1000} placeholder={service.target === "video" ? "填写服务商 API 地址" : "https://api.openai.com/v1"} /></label>
    <label>模型名称<input value={model} onChange={(event) => setModel(event.target.value)} maxLength={120} placeholder={service.target === "video" ? "填写视频模型" : "填写模型标识"} /></label>
    <label>API Key{service.has_api_key && <span className="credential-state">已配置 · {service.key_source === "workspace" ? "工作区密钥" : "环境默认密钥"}</span>}<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} maxLength={4096} placeholder={service.has_api_key ? "留空则保留已保存密钥" : "输入服务商 API Key"} /></label>
    {service.key_source === "workspace" && <label className="clear-key-option"><input type="checkbox" checked={clearKey} onChange={(event) => setClearKey(event.target.checked)} />清除工作区已保存的密钥</label>}
    <div className="section-actions"><button className="button primary" disabled={busy}>保存配置</button><button className="button secondary" type="button" disabled={busy} onClick={check}>检查连接</button></div>
    {result && <p className={`check-result ${result.ok ? "ok" : "error"}`} role="status">{result.message}</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
  </form>;
}

function PlatformRow({ item, workspaceId, refresh }: { item: PlatformAccount; workspaceId: number; refresh: () => Promise<void> }) {
  const [identifier, setIdentifier] = useState(item.account_identifier);
  const [status, setStatus] = useState(item.authorization_status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await settingsRequest(`platform-accounts/${item.store_id}`, workspaceId, { method: "PATCH", body: JSON.stringify({ account_identifier: identifier, authorization_status: status }) });
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return <form className="platform-row" onSubmit={save}>
    <div><strong>{item.store_name}</strong><small>{item.platform} · 店铺 {item.store_id}</small></div>
    <label>平台账号标识<input value={identifier} onChange={(event) => setIdentifier(event.target.value)} maxLength={120} placeholder="仅填写账号标识" /></label>
    <label>本地状态<UiSelect value={status} onChange={(value) => setStatus(value as PlatformAccount["authorization_status"])} ariaLabel="平台授权状态" options={[{ value: "not_connected", label: "未授权" }, { value: "placeholder", label: "占位记录" }]} /></label>
    <button className="button secondary" disabled={busy}>保存</button>
    {error && <p className="notice error" role="alert">{error}</p>}
  </form>;
}

export function SettingsWorkbench({ workspaceId }: { workspaceId: number }) {
  const [data, setData] = useState<SettingsData | null>(null);
  const [audit, setAudit] = useState<ConfigAudit[]>([]);
  const [error, setError] = useState("");
  const [rulesBusy, setRulesBusy] = useState(false);
  const [rulesMessage, setRulesMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [nextData, nextAudit] = await Promise.all([
        settingsRequest<SettingsData>("", workspaceId),
        settingsRequest<ConfigAudit[]>("audit", workspaceId),
      ]);
      setData(nextData); setAudit(nextAudit); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "配置加载失败"); }
  }, [workspaceId]);

  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(timer); }, [load]);

  async function saveRules(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setRulesBusy(true); setRulesMessage("");
    const values = new FormData(event.currentTarget);
    const fields: (keyof TaskRules)[] = ["timeout_seconds", "max_retries", "max_concurrency", "image_poll_interval_seconds", "image_poll_max_attempts", "video_poll_interval_seconds", "video_poll_max_attempts"];
    const payload = Object.fromEntries(fields.map((field) => [field, Number(values.get(field))]));
    try {
      await settingsRequest("rules", workspaceId, { method: "PUT", body: JSON.stringify(payload) });
      setRulesMessage("任务规则已保存，变更记录已写入审计。"); await load();
    } catch (cause) { setRulesMessage(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setRulesBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">SYSTEM SETTINGS</p><h1>系统设置</h1><p>管理模型服务、店铺授权信息、任务规则和配置记录。</p></div></div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!data ? <p className="panel">正在加载配置…</p> : <>
      <section className="settings-services" aria-label="模型服务配置">
        {data.services.map((service) => <ServiceCard key={`${service.target}:${service.provider}:${service.model}`} service={service} workspaceId={workspaceId} refresh={load} />)}
      </section>
      <p className="settings-note">连接检查会向服务商发送模型元数据请求，不生成文本、图片或视频。成功只说明模型元数据可访问，不能证明生成权限或额度；视频检查将在供应商适配完成后开放。</p>
      <div className="settings-lower">
        <section className="panel"><h2>用户与工作区权限</h2><div className="permission-row"><strong>管理员</strong><span>维护服务、任务规则和平台占位信息</span></div><div className="permission-row"><strong>运营主管</strong><span>运营资料与后续高风险审批</span></div><div className="permission-row"><strong>运营人员</strong><span>运营资料编辑，不能修改系统配置</span></div></section>
        <section className="panel"><h2>平台账号与授权状态</h2><p className="subtle">只记录店铺对应的账号标识与占位状态；不保存平台密码、Cookie 或授权令牌。</p>{data.platforms.length ? data.platforms.map((item) => <PlatformRow key={`${item.store_id}:${item.account_identifier}:${item.authorization_status}`} item={item} workspaceId={workspaceId} refresh={load} />) : <p className="subtle">还没有店铺。</p>}</section>
      </div>
      <section className="panel"><div className="section-heading"><div><p className="eyebrow">TASK RULES</p><h2>异步任务运行参数</h2></div><span className="muted-tag">供后续生成任务使用</span></div><form className="rules-form" onSubmit={saveRules}>
        {([ ["timeout_seconds", "任务超时（秒）", 30, 3600], ["max_retries", "失败重试上限", 0, 10], ["max_concurrency", "最大并发数", 1, 32], ["image_poll_interval_seconds", "图片轮询间隔（秒）", 2, 120], ["image_poll_max_attempts", "图片轮询上限", 1, 100], ["video_poll_interval_seconds", "视频轮询间隔（秒）", 2, 120], ["video_poll_max_attempts", "视频轮询上限", 1, 100] ] as const).map(([field, label, min, max]) => <label key={field}>{label}<input name={field} type="number" min={min} max={max} required defaultValue={data.rules[field]} /></label>)}
        <button className="button primary" disabled={rulesBusy}>保存任务规则</button>
      </form>{rulesMessage && <p className="subtle" role="status">{rulesMessage}</p>}</section>
      <section className="panel"><div className="section-heading"><div><p className="eyebrow">CONFIG AUDIT</p><h2>配置修改记录</h2></div><span className="muted-tag">最近 {audit.length} 条</span></div>{audit.length ? <div className="audit-list">{audit.map((item) => <div key={item.id}><strong>{auditLabels[item.action] ?? item.action}</strong><span>{item.actor_name} · {new Date(item.created_at).toLocaleString("zh-CN")}</span><small>{item.resource_type} {item.resource_id ?? ""}</small></div>)}</div> : <p className="subtle">暂无配置变更记录。</p>}</section>
    </>}
  </>;
}

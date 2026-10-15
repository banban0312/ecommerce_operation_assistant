import { HealthPanel } from "@/components/health-panel";
import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { fetchApiHealth, type HealthReport } from "@/lib/health";

export const dynamic = "force-dynamic";

// 菜单先展示规划中的模块；对应 Issue 完成前保持禁用，避免误导用户。
const navigation = ["商品工作台", "创意与素材", "生成任务", "投放与复盘", "导入中心", "Agent 任务", "系统配置"];
const roleLabels: Record<string, string> = {
  operator: "运营人员",
  supervisor: "运营主管",
  admin: "管理员",
};

export default async function Dashboard() {
  const cookieStore = await cookies();
  const token = cookieStore.get("eoa_access_token")?.value;
  if (!token) redirect("/login");

  const apiBase = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  let identityResponse: Response;
  try {
    identityResponse = await fetch(new URL("/api/v1/auth/me", apiBase), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    redirect("/login");
  }
  if (!identityResponse.ok) redirect("/login");
  const currentUser: {
    display_name: string;
    email: string;
    memberships: { workspace_name: string; role: string }[];
  } = await identityResponse.json();

  // 服务端先读取基础服务状态，客户端面板加载后仍可手动刷新。
  let report: HealthReport;
  try {
    report = await fetchApiHealth();
  } catch {
    report = { service: "api", status: "degraded", checks: {} };
  }
  const docsUrl = new URL("/docs", process.env.API_PUBLIC_URL ?? "http://localhost:8000").href;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="电商运营助手首页">
          <span className="brand-icon" aria-hidden="true">E</span>
          <span>电商运营助手<small>ECOMMERCE WORKSPACE</small></span>
        </Link>
        <p className="nav-label">运营工作台</p>
        <nav aria-label="主导航">
          <Link className="nav-item active" href="/" aria-current="page"><span aria-hidden="true">◫</span>运营大盘</Link>
          {navigation.map((name) => (
            <button key={name} className="nav-item" disabled title="将在后续迭代开放">
              <span aria-hidden="true">◇</span>{name}<small>待开放</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" />本地开发环境</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">工作台 <span>/</span> <strong>运营大盘</strong></div>
          <div className="account-menu">
            <span className="environment-tag">{currentUser.memberships[0]?.workspace_name ?? "工作区"} · {roleLabels[currentUser.memberships[0]?.role ?? ""] ?? "成员"}</span>
            <span className="account-name">{currentUser.display_name}</span>
            <form action="/api/auth/logout" method="post"><button className="button secondary" type="submit">退出登录</button></form>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>运营大盘</h1><p>让商品、内容和经营结果，在同一个工作台连接起来。</p></div>
            <a className="button secondary" href={docsUrl} target="_blank" rel="noreferrer">查看 API 文档 ↗</a>
          </div>
          <section className="welcome-panel">
            <div><span className="welcome-label">从单品建档，走向经营闭环</span><h2>你的运营工作台，正在搭建中</h2><p>商品建档、智能诊断与创意制作将逐步开放，先检查下方基础服务状态。</p><span className="stage-tag">当前阶段：工程基线与服务连接</span></div>
            <div className="welcome-art" aria-hidden="true"><span className="art-square" /><span className="art-square small" /><span className="art-line" /></div>
          </section>
          <HealthPanel initialReport={report} />
          <section className="panel empty-panel" aria-labelledby="products-title">
            <div className="section-heading"><div><p className="eyebrow">商品概览</p><h2 id="products-title">开启第一轮单品运营</h2></div><span className="muted-tag">后续迭代开放</span></div>
            <div className="empty-state"><span className="empty-icon" aria-hidden="true">▱</span><h3>商品建档功能准备中</h3><p>完成登录权限与商品模块后，你可以在这里创建店铺、维护 SKU，开始单品诊断。</p><button className="button primary" disabled>新建商品 · 待开放</button></div>
          </section>
          <footer className="page-footer">电商运营助手 <span>AI 辅助运营 · 人工决策</span></footer>
        </main>
      </div>
    </div>
  );
}

import Link from "next/link";
import type { Identity } from "@/lib/identity";

const roleLabels: Record<string, string> = {
  operator: "运营人员",
  supervisor: "运营主管",
  admin: "管理员",
};

export function WorkspaceShell({ identity, title, children }: { identity: Identity; title: string; children: React.ReactNode }) {
  const membership = identity.memberships[0];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="电商运营助手首页">
          <span className="brand-icon" aria-hidden="true">E</span>
          <span>电商运营助手<small>ECOMMERCE WORKSPACE</small></span>
        </Link>
        <p className="nav-label">运营工作台</p>
        <nav aria-label="主导航">
          <Link className={`nav-item ${title === "运营大盘" ? "active" : ""}`} href="/"><span aria-hidden="true">◫</span>运营大盘</Link>
          <Link className={`nav-item ${title === "商品工作台" ? "active" : ""}`} href="/#products"><span aria-hidden="true">▱</span>商品工作台</Link>
          {["创意与素材", "生成任务", "投放与复盘", "导入中心", "Agent 任务", "系统配置"].map((name) => (
            <button key={name} className="nav-item" disabled title="将在后续迭代开放"><span aria-hidden="true">◇</span>{name}<small>待开放</small></button>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" />本地开发环境</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">工作台 <span>/</span> <strong>{title}</strong></div>
          <div className="account-menu">
            <span className="environment-tag">{membership?.workspace_name ?? "工作区"} · {roleLabels[membership?.role ?? ""] ?? "成员"}</span>
            <span className="account-name">{identity.display_name}</span>
            <form action="/api/auth/logout" method="post"><button className="button secondary" type="submit">退出登录</button></form>
          </div>
        </header>
        <main>{children}<footer className="page-footer">电商运营助手 <span>AI 辅助运营 · 人工决策</span></footer></main>
      </div>
    </div>
  );
}

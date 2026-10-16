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
      <div className="workspace">
        <header className="topbar">
          <Link className="brand" href="/" aria-label="电商运营助手首页">
            <span className="brand-icon" aria-hidden="true">E</span>
            <span>电商运营助手<small>ECOMMERCE WORKSPACE</small></span>
          </Link>
          <nav className="primary-nav" aria-label="主导航">
            <Link className={`nav-item ${title === "运营大盘" ? "active" : ""}`} href="/">运营大盘</Link>
            <Link className={`nav-item ${title === "商品工作台" ? "active" : ""}`} href="/products">商品工作台</Link>
            {["Agent 中心", "导入中心"].map((name) => (
              <button key={name} className="nav-item" disabled title="将在后续迭代开放">{name}</button>
            ))}
            {membership?.role === "admin" ? <Link className={`nav-item ${title === "模型配置" ? "active" : ""}`} href="/settings">模型配置</Link> : <button className="nav-item" disabled title="仅管理员可用">模型配置</button>}
          </nav>
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

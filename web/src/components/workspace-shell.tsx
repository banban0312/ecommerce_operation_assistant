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
            <Link className={`nav-item ${title === "Agent 中心" ? "active" : ""}`} href="/agent">Agent 中心</Link>
            <Link className={`nav-item ${title === "导入中心" ? "active" : ""}`} href="/imports">导入中心</Link>
            {membership?.role === "admin" && <>
              <Link className={`nav-item ${title === "成员管理" ? "active" : ""}`} href="/members">成员管理</Link>
              <Link className={`nav-item ${title === "系统设置" ? "active" : ""}`} href="/settings">系统设置</Link>
            </>}
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

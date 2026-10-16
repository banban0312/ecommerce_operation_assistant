"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { membersRequest, type CreateMember, type WorkspaceMember } from "@/lib/members";

const roleLabels: Record<WorkspaceMember["role"], string> = {
  admin: "管理员",
  supervisor: "运营主管",
  operator: "运营人员",
};

const roleDescriptions: Record<WorkspaceMember["role"], string> = {
  admin: "管理工作区成员、模型服务和任务配置。",
  supervisor: "处理高风险审批，并查看运营工作区数据。",
  operator: "维护日常商品与运营资料。",
};

export function MembersWorkbench({ workspaceId }: { workspaceId: number }) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [role, setRole] = useState<CreateMember["role"]>("operator");
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setMembers(await membersRequest<WorkspaceMember[]>(workspaceId));
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "成员列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await membersRequest<Pick<WorkspaceMember, "display_name" | "role">>(workspaceId, {
        method: "POST",
        body: JSON.stringify({
          email: values.get("email"),
          display_name: values.get("display_name"),
          password: values.get("password"),
          role,
        }),
      });
      form.reset();
      setRole("operator");
      await load();
      setNotice(`已将 ${created.display_name} 添加为${roleLabels[created.role]}。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "成员创建失败");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <div className="page-heading">
      <div><p className="eyebrow">WORKSPACE ACCESS</p><h1>成员与角色</h1><p>管理当前工作区成员，为每位成员分配合适的操作权限。</p></div>
      <span className="muted-tag">工作区 #{workspaceId} · 管理员专用</span>
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {notice && <p className="notice success" role="status">{notice}</p>}

    <section className="member-role-guide" aria-label="角色权限说明">
      {(Object.keys(roleLabels) as WorkspaceMember["role"][]).map((item, index) => (
        <article className="member-role-card" key={item}>
          <span className="member-role-number">0{index + 1}</span>
          <div><h2>{roleLabels[item]}</h2><p>{roleDescriptions[item]}</p></div>
        </article>
      ))}
    </section>

    <section className="panel member-create-panel">
      <div className="section-heading"><div><p className="eyebrow">ADD WORKSPACE MEMBER</p><h2>创建成员账号</h2><p className="subtle">新账号会加入当前工作区，并立即获得所选角色权限。</p></div></div>
      <form className="member-create-form" onSubmit={createMember}>
        <label>成员姓名<input name="display_name" required maxLength={120} placeholder="例如：林晓运营" /></label>
        <label>登录邮箱<input name="email" type="email" required maxLength={255} placeholder="name@example.com" /></label>
        <label>初始密码<input name="password" type="password" required minLength={12} maxLength={256} autoComplete="new-password" placeholder="至少 12 位" /></label>
        <div className="member-role-field"><span className="member-field-label">工作区角色</span><button className="member-role-trigger" type="button" aria-haspopup="listbox" aria-expanded={roleMenuOpen} onClick={() => setRoleMenuOpen((open) => !open)}><span><strong>{roleLabels[role]}</strong><small>{roleDescriptions[role]}</small></span><span className="member-role-chevron" aria-hidden="true">⌄</span></button>{roleMenuOpen && <div className="member-role-options" role="listbox" aria-label="选择工作区角色">{(Object.keys(roleLabels) as WorkspaceMember["role"][]).map((item) => <button type="button" role="option" aria-selected={role === item} className={role === item ? "selected" : ""} key={item} onClick={() => { setRole(item); setRoleMenuOpen(false); }}><span><strong>{roleLabels[item]}</strong><small>{roleDescriptions[item]}</small></span>{role === item && <span aria-hidden="true">✓</span>}</button>)}</div>}</div>
        <div className="member-create-footer"><p>初始密码由你设置，请通过安全方式告知成员。若邮箱已有账号，只会加入当前工作区，不会修改原密码。</p><button className="button primary" disabled={busy}>{busy ? "正在创建…" : "创建成员"}</button></div>
      </form>
    </section>

    <section className="panel member-list-panel">
      <div className="section-heading"><div><p className="eyebrow">CURRENT MEMBERS</p><h2>当前工作区成员</h2></div><span className="muted-tag">{members.length} 位成员</span></div>
      {loading ? <p className="subtle">正在加载成员…</p> : members.length ? <div className="member-list">
        <div className="member-list-head"><span>成员</span><span>角色</span><span>状态</span><span>最近登录</span></div>
        {members.map((member) => <article className="member-list-row" key={member.id}>
          <div className="member-identity"><span className="member-avatar">{member.display_name.slice(0, 1)}</span><span><strong>{member.display_name}</strong><small>{member.email}</small></span></div>
          <span className={`member-role-badge ${member.role}`}>{roleLabels[member.role]}</span>
          <span className={`member-state ${member.status}`}>{member.status === "active" ? "正常" : "已停用"}</span>
          <time>{member.last_login_at ? new Date(member.last_login_at).toLocaleString("zh-CN") : "尚未登录"}</time>
        </article>)}
      </div> : <p className="subtle">当前工作区还没有成员。</p>}
    </section>
  </>;
}

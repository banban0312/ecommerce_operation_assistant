import { SettingsWorkbench } from "@/components/settings-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const identity = await requireIdentity();
  const membership = identity.memberships[0];
  return (
    <WorkspaceShell identity={identity} title="模型配置">
      {membership?.role === "admin" ? <SettingsWorkbench workspaceId={membership.workspace_id} /> : <p className="notice error">仅工作空间管理员可以访问系统配置。</p>}
    </WorkspaceShell>
  );
}

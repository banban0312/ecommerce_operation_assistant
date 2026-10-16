import { MembersWorkbench } from "@/components/members-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function MembersPage() {
  const identity = await requireIdentity();
  const membership = identity.memberships[0];
  return (
    <WorkspaceShell identity={identity} title="成员管理">
      {membership?.role === "admin"
        ? <MembersWorkbench workspaceId={membership.workspace_id} />
        : <p className="notice error">仅工作空间管理员可以管理成员。</p>}
    </WorkspaceShell>
  );
}

import { ImportWorkbench } from "@/components/import-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";
export const dynamic = "force-dynamic";
export default async function ImportsPage(){const identity=await requireIdentity();const workspaceId=identity.memberships[0]?.workspace_id;return <WorkspaceShell identity={identity} title="导入中心">{workspaceId?<ImportWorkbench workspaceId={workspaceId}/>:<p className="notice error">当前账号没有可用工作空间。</p>}</WorkspaceShell>}

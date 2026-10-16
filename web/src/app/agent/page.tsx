import { AgentWorkbench } from "@/components/agent-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";
export const dynamic = "force-dynamic";
export default async function AgentPage(){const identity=await requireIdentity();const workspaceId=identity.memberships[0]?.workspace_id;return <WorkspaceShell identity={identity} title="Agent 中心">{workspaceId?<AgentWorkbench workspaceId={workspaceId}/>:<p className="notice error">当前账号没有可用工作空间。</p>}</WorkspaceShell>}

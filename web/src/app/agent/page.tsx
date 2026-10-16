import { AgentWorkbench } from "@/components/agent-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";
export const dynamic = "force-dynamic";
export default async function AgentPage({ searchParams }: { searchParams: Promise<{ product_id?: string }> }) { const [identity, params] = await Promise.all([requireIdentity(), searchParams]); const workspaceId = identity.memberships[0]?.workspace_id; const initialProductId = /^\d+$/.test(params.product_id ?? "") ? params.product_id : ""; return <WorkspaceShell identity={identity} title="Agent 中心">{workspaceId ? <AgentWorkbench workspaceId={workspaceId} initialProductId={initialProductId} /> : <p className="notice error">当前账号没有可用工作空间。</p>}</WorkspaceShell>; }

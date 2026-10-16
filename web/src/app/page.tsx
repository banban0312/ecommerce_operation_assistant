import { CatalogDashboard } from "@/components/catalog-dashboard";
import { HealthPanel } from "@/components/health-panel";
import { WorkspaceShell } from "@/components/workspace-shell";
import { fetchApiHealth, type HealthReport } from "@/lib/health";
import { requireIdentity } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const identity = await requireIdentity();
  const workspaceId = identity.memberships[0]?.workspace_id;
  let report: HealthReport;
  try {
    report = await fetchApiHealth();
  } catch {
    report = { service: "api", status: "degraded", checks: {} };
  }
  return (
    <WorkspaceShell identity={identity} title="运营大盘">
      <div className="page-heading"><div><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>运营大盘</h1><p>查看店铺、商品和库存状态，进入单品工作台。</p></div></div>
      {workspaceId ? <CatalogDashboard workspaceId={workspaceId} canSeedDemo={["admin", "supervisor"].includes(identity.memberships[0]?.role ?? "")} /> : <p className="notice error">当前账号没有可用工作空间。</p>}
      <HealthPanel initialReport={report} />
    </WorkspaceShell>
  );
}

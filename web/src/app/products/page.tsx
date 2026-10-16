import { ProductHub } from "@/components/product-hub";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function ProductsPage({ searchParams }: { searchParams: Promise<{ store_id?: string }> }) {
  const identity = await requireIdentity();
  const { store_id } = await searchParams;
  const workspaceId = identity.memberships[0]?.workspace_id;
  return (
    <WorkspaceShell identity={identity} title="商品工作台">
      {workspaceId ? <ProductHub workspaceId={workspaceId} initialStoreId={store_id && /^\d+$/.test(store_id) ? store_id : ""} /> : <p className="notice error">当前账号没有可用工作空间。</p>}
    </WorkspaceShell>
  );
}

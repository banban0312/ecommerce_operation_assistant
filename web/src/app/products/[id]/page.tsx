import { ProductWorkbench } from "@/components/product-workbench";
import { WorkspaceShell } from "@/components/workspace-shell";
import { requireIdentity } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const identity = await requireIdentity();
  const { id } = await params;
  const productId = Number(id);
  const workspaceId = identity.memberships[0]?.workspace_id;
  return (
    <WorkspaceShell identity={identity} title="商品工作台">
      {workspaceId && Number.isSafeInteger(productId) && productId > 0 ? <ProductWorkbench productId={productId} workspaceId={workspaceId} /> : <p className="notice error">商品地址不正确。</p>}
    </WorkspaceShell>
  );
}

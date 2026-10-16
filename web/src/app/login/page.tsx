import { LoginForm } from "@/components/login-form";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="login-shell">
      <div className="login-layout">
        <section className="login-showcase" aria-label="工作台介绍">
          <div className="login-showcase-orbit orbit-one" aria-hidden="true" />
          <div className="login-showcase-orbit orbit-two" aria-hidden="true" />
          <div className="login-showcase-content">
            <div className="login-brand"><span className="login-brand-mark" aria-hidden="true">E</span><span>电商运营助手<small>ECOMMERCE OPS STUDIO</small></span></div>
            <p className="login-showcase-kicker">ONE WORKSPACE · CLEAR DECISIONS</p>
            <h2>把经营数据与运营动作，放在同一条工作流里。</h2>
            <p className="login-showcase-intro">从商品建档、竞品分析到内容创意与经营复盘，让运营过程清晰可查，每项重要决策都由人确认。</p>
            <div className="login-preview" aria-label="运营工作流预览">
              <div className="login-preview-head"><span><i /> 工作区经营概览</span><small>本月</small></div>
              <div className="login-preview-metric"><div><small>商品经营表现</small><strong>持续跟踪</strong></div><span>↗</span></div>
              <div className="login-preview-chart" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>
              <div className="login-preview-steps"><span><b>01</b> 商品洞察</span><span><b>02</b> 创意生成</span><span><b>03</b> 人工审批</span></div>
            </div>
            <p className="login-showcase-foot">安全工作区 · 角色权限 · 操作留痕</p>
          </div>
        </section>
        <section className="login-card" aria-labelledby="login-title">
          <div className="brand-icon" aria-hidden="true">E</div>
          <p className="eyebrow">WELCOME BACK</p>
          <h1 id="login-title">登录运营工作台</h1>
          <p className="login-intro">使用管理员提供的工作账号进入你的工作空间。</p>
          <LoginForm />
          <p className="login-card-foot">遇到登录问题？请联系你的工作区管理员。</p>
        </section>
      </div>
    </main>
  );
}

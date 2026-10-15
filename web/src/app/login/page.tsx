import { LoginForm } from "@/components/login-form";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-icon" aria-hidden="true">E</div>
        <p className="eyebrow">ECOMMERCE WORKSPACE</p>
        <h1 id="login-title">登录运营工作台</h1>
        <p className="login-intro">使用管理员提供的工作账号进入你的工作空间。</p>
        <LoginForm />
      </section>
    </main>
  );
}

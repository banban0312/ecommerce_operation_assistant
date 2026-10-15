"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function LoginForm() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    const formData = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password"),
        }),
      });
      const result = (await response.json()) as { message?: string };
      if (!response.ok) {
        setMessage(result.message ?? "登录失败，请检查输入后重试。");
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setMessage("暂时无法连接服务，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="email">邮箱</label>
      <input id="email" name="email" type="email" autoComplete="username" required maxLength={255} />
      <label htmlFor="password">密码</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required maxLength={256} />
      {message && <p className="login-error" role="alert">{message}</p>}
      <button className="button primary login-submit" type="submit" disabled={submitting}>
        {submitting ? "正在登录…" : "登录工作台"}
      </button>
    </form>
  );
}

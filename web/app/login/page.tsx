"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Button, Card, ErrorState, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("leader");
  const [password, setPassword] = useState("Leader@123");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/chat");
    }
  }, [loading, user, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-xl font-semibold">登录</h1>
        <p className="mt-1 text-sm text-slate-500">企业知识库工单系统</p>
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="mb-1 block text-sm text-slate-600">用户名</label>
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">密码</label>
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error ? <ErrorState message={error} /> : null}
          <Button className="w-full" disabled={submitting}>
            {submitting ? "登录中..." : "登录"}
          </Button>
        </form>
        <p className="mt-4 text-xs text-slate-400">
          预置账号：leader / employee1 / employee2
        </p>
      </Card>
    </div>
  );
}

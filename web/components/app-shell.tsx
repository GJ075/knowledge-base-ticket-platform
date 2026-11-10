"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Spinner } from "./ui";

const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/chat", label: "问答", roles: ["employee", "leader"] },
  { href: "/history", label: "我的历史", roles: ["employee", "leader"] },
  { href: "/documents", label: "文档", roles: ["employee", "leader"] },
  {
    href: "/documents/approvals",
    label: "文档审批",
    roles: ["leader"],
  },
  { href: "/tickets", label: "工单", roles: ["employee", "leader"] },
  { href: "/tickets/new", label: "新建工单", roles: ["employee", "leader"] },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return <Spinner label="正在加载登录状态" />;
  }
  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4">
          <p className="text-sm font-semibold text-slate-900">
            企业知识库工单系统
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {user.display_name} · {user.role === "leader" ? "领导" : "员工"}
          </p>
        </div>
        <nav className="space-y-1 p-3">
          {NAV.filter((item) => item.roles.includes(user.role)).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100",
                pathname === item.href &&
                  "bg-slate-900 text-white hover:bg-slate-900",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3">
          <button
            className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-100"
            onClick={() => void logout()}
          >
            退出登录
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
    </div>
  );
}

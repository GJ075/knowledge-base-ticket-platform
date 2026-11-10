import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth";
import { QueryProvider } from "@/lib/query";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业知识库工单系统",
  description: "企业知识库问答与工单处理系统",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <QueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}

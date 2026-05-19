import type { Metadata } from "next";
import "./globals.css";
import { Layout } from "@/components/Layout";

export const metadata: Metadata = {
  title: "法律分析仪器",
  description: "RAG 合同法律系统可视化分析平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full bg-slate-950 text-slate-100">
        <Layout>{children}</Layout>
      </body>
    </html>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, GitBranch, Home, MessageSquare, FlaskConical, LayoutDashboard } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "首页", icon: Home },
  { href: "/drift", label: "法律漂移", icon: Activity },
  { href: "/domino", label: "多米诺效应", icon: GitBranch },
  { href: "/visualize", label: "可视化分析", icon: LayoutDashboard },
  { href: "/ask", label: "法律咨询", icon: MessageSquare },
  { href: "/counterfactual", label: "反事实模拟", icon: FlaskConical },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-slate-800 bg-slate-900/50 backdrop-blur-sm">
        <div className="flex h-14 items-center border-b border-slate-800 px-4">
          <span className="text-sm font-semibold tracking-wide text-slate-200">
            法律分析仪器
          </span>
        </div>
        <nav className="space-y-0.5 p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-slate-800 text-slate-50 font-medium"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl p-6">{children}</div>
      </main>
    </div>
  );
}

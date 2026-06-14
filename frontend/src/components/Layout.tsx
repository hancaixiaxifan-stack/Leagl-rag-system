"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ChevronDown,
  FlaskConical,
  LayoutDashboard,
  MessageSquare,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/visualize", label: "可视化分析", eyebrow: "GRAPH", icon: LayoutDashboard },
  { href: "/drift", label: "法律漂移", eyebrow: "DRIFT", icon: Activity },
  { href: "/ask", label: "法律咨询", eyebrow: "ASK", icon: MessageSquare },
  { href: "/counterfactual", label: "反事实模拟", eyebrow: "SIM", icon: FlaskConical },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  const activeItem = useMemo(
    () => navItems.find((item) => pathname === item.href) ?? navItems[0],
    [pathname]
  );
  const ActiveIcon = activeItem.icon;
  const isCanvasPage = pathname === "/visualize" || pathname === "/counterfactual";
  const isFixedPage = pathname === "/visualize" || pathname === "/ask" || pathname === "/counterfactual";

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  return (
    <div className={cn("bg-[#f8f6f1] text-[#1f2933]", isFixedPage ? "h-screen overflow-hidden" : "min-h-screen")}>
      <div
        className="fixed left-1/2 top-3 z-50 w-[min(calc(100vw-1.5rem),560px)] -translate-x-1/2"
        onMouseEnter={() => setNavOpen(true)}
        onMouseLeave={() => setNavOpen(false)}
      >
        <button
          type="button"
          onClick={() => setNavOpen((open) => !open)}
          aria-expanded={navOpen}
          className="mx-auto flex h-11 max-w-max items-center gap-3 rounded-full border border-[#ded7ca]/80 bg-[#fffefa]/78 px-3.5 text-sm font-medium text-[#1f2933] shadow-[0_16px_48px_rgba(31,41,51,0.13)] backdrop-blur-xl transition-all duration-200 hover:border-[#cfc5b5] hover:bg-[#fffefa]/92 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f3a5f]"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1f3a5f] text-[#fffefa]">
            <ActiveIcon className="h-3.5 w-3.5" />
          </span>
          <span className="hidden text-[11px] font-semibold tracking-[0.18em] text-[#8a7f6c] sm:inline">
            LEGAL RESEARCH
          </span>
          <span className="h-4 w-px bg-[#ded7ca]" />
          <span>{activeItem.label}</span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-[#8a7f6c] transition-transform duration-200",
              navOpen && "rotate-180"
            )}
          />
        </button>

        <div
          className={cn(
            "mx-auto mt-2 overflow-hidden rounded-2xl border border-[#ded7ca]/85 bg-[#fffefa]/86 shadow-[0_22px_70px_rgba(31,41,51,0.18)] backdrop-blur-2xl transition-all duration-200",
            navOpen
              ? "max-h-72 translate-y-0 opacity-100"
              : "pointer-events-none max-h-0 -translate-y-2 opacity-0"
          )}
        >
          <div className="grid gap-2 p-2 sm:grid-cols-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setNavOpen(false)}
                  className={cn(
                    "group flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm transition-all duration-200",
                    active
                      ? "border-[#1f3a5f] bg-[#1f3a5f] text-[#fffefa] shadow-sm"
                      : "border-transparent text-[#5f574a] hover:border-[#ded7ca] hover:bg-[#f7f3eb] hover:text-[#1f2933]"
                  )}
                >
                  <span
                    className={cn(
                      "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                      active
                        ? "border-[#fffefa]/20 bg-[#fffefa]/12"
                        : "border-[#e4ded3] bg-[#fffefa] group-hover:border-[#cfc5b5]"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span>
                    <span className="block text-[10px] font-semibold tracking-[0.16em] opacity-65">
                      {item.eyebrow}
                    </span>
                    <span className="block font-medium">{item.label}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <main className={cn("bg-[#f8f6f1]", isFixedPage ? "h-screen overflow-hidden" : "min-h-screen overflow-auto")}>
        <div
          className={cn(
            "mx-auto w-full",
            isCanvasPage
              ? "h-full max-w-none overflow-hidden px-3 pb-3 pt-14 sm:px-4"
              : pathname === "/ask"
              ? "h-full max-w-6xl overflow-hidden px-5 pb-5 pt-16 sm:px-6"
              : "max-w-7xl px-5 pb-8 pt-20 sm:px-6"
          )}
        >
          {children}
        </div>
      </main>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  AlertTriangle,
  Video,
  Tag,
  Activity,
  ChevronRight,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/",              label: "Dashboard",        icon: LayoutDashboard, section: "monitor" },
  { href: "/anomalies",     label: "Anomaly Explorer", icon: AlertTriangle,   section: "monitor" },
  { href: "/trips",         label: "Video Library",    icon: Video,           section: "data"    },
  { href: "/admin/label",   label: "Label Queue",      icon: Tag,             section: "admin"   },
];

const SECTIONS: Record<string, string> = {
  monitor: "Monitor",
  data:    "Data",
  admin:   "Admin",
};

export function Sidebar() {
  const pathname = usePathname();

  const grouped = Object.entries(SECTIONS).map(([key, title]) => ({
    key,
    title,
    items: NAV_ITEMS.filter(n => n.section === key),
  }));

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex flex-col bg-surface border-r border-border"
           style={{ width: "var(--sidebar-width)" }}>
      {/* Wordmark */}
      <div className="px-5 pt-6 pb-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-amber-DEFAULT rounded-sm flex items-center justify-center flex-shrink-0"
               style={{ boxShadow: "0 0 12px rgba(245,158,11,0.4)" }}>
            <Activity size={14} className="text-void" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-display text-[17px] font-800 tracking-wide text-ink-primary leading-none"
                 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, letterSpacing: "0.04em" }}>
              DASHCAM<span style={{ color: "var(--color-amber)" }}>IQ</span>
            </div>
            <div className="text-label text-ink-tertiary" style={{ fontSize: "8px", letterSpacing: "0.12em" }}>
              ANOMALY DETECTION
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
        {grouped.map(({ key, title, items }) => (
          <div key={key}>
            <p className="section-label px-2 mb-2" style={{ fontSize: "8px" }}>{title}</p>
            <ul className="space-y-0.5">
              {items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || (href !== "/" && pathname.startsWith(href));
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      className={cn(
                        "nav-link flex items-center gap-3 px-3 py-2.5 rounded-sm text-[13px] font-medium",
                        active
                          ? "active"
                          : "text-ink-secondary hover:text-ink-primary"
                      )}
                    >
                      <Icon size={15} strokeWidth={active ? 2 : 1.5} />
                      <span className="flex-1 leading-none">{label}</span>
                      {active && <ChevronRight size={10} className="opacity-60" />}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Status indicator */}
      <div className="px-4 py-4 border-t border-border">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-label text-ink-tertiary">SYSTEM ONLINE</span>
        </div>
        <div className="mt-1.5 text-label text-ink-tertiary opacity-60"
             style={{ fontSize: "8px" }}>
          v1.0 · PRODUCTION
        </div>
      </div>
    </aside>
  );
}

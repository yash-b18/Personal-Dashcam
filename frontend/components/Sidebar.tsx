"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  AlertTriangle,
  Video,
  Tag,
  Activity,
  Zap,
} from "lucide-react";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Dashboard",
    sublabel: "Scores & overview",
    icon: LayoutDashboard,
    shortcut: "⌘1",
  },
  {
    href: "/anomalies",
    label: "Anomaly Explorer",
    sublabel: "Browse incidents",
    icon: AlertTriangle,
    shortcut: "⌘2",
  },
  {
    href: "/trips",
    label: "Video Library",
    sublabel: "All recorded clips",
    icon: Video,
    shortcut: "⌘3",
  },
  {
    href: "/admin/label",
    label: "Label Queue",
    sublabel: "Ground truth",
    icon: Tag,
    shortcut: "⌘4",
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        bottom: 0,
        zIndex: 40,
        width: "var(--sidebar-width)",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(160deg, #08121f 0%, #060d18 60%, #07101e 100%)",
        borderRight: "1px solid rgba(34,211,238,0.07)",
      }}
    >
      {/* Top accent line */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: "1px",
        background: "linear-gradient(90deg, transparent 0%, rgba(34,211,238,0.45) 40%, rgba(59,130,246,0.35) 70%, transparent 100%)",
      }} />

      {/* Ambient top glow */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: "120px", pointerEvents: "none",
        background: "radial-gradient(ellipse 140% 80% at 30% 0%, rgba(34,211,238,0.05) 0%, transparent 70%)",
      }} />

      {/* ── Wordmark ─────────────────────────────────────── */}
      <div style={{ padding: "22px 18px 20px", borderBottom: "1px solid rgba(28,45,68,0.5)", position: "relative" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "11px" }}>
          {/* Logo mark */}
          <div style={{
            width: "36px", height: "36px", borderRadius: "10px", flexShrink: 0,
            background: "linear-gradient(135deg, rgba(34,211,238,0.18) 0%, rgba(59,130,246,0.14) 100%)",
            border: "1px solid rgba(34,211,238,0.22)",
            display: "flex", alignItems: "center", justifyContent: "center",
            position: "relative", overflow: "hidden",
            boxShadow: "0 0 18px rgba(34,211,238,0.12), inset 0 1px 0 rgba(255,255,255,0.06)",
          }}>
            <Activity size={16} color="#22D3EE" strokeWidth={2} style={{ filter: "drop-shadow(0 0 5px rgba(34,211,238,0.7))" }} />
            {/* Sweep shimmer */}
            <div style={{
              position: "absolute", inset: 0,
              background: "linear-gradient(105deg, transparent 35%, rgba(34,211,238,0.1) 50%, transparent 65%)",
              animation: "logo-sweep 4s ease-in-out infinite",
            }} />
          </div>

          <div>
            {/* Gradient wordmark */}
            <div style={{
              fontFamily: "var(--font-jakarta)", fontWeight: 800, fontSize: "15px",
              letterSpacing: "-0.025em", lineHeight: 1.1,
              background: "linear-gradient(100deg, #EAF2FF 0%, #22D3EE 120%)",
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
            }}>
              DashcamIQ
            </div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: "0.2em",
              color: "rgba(61,90,128,0.65)", marginTop: "2px", textTransform: "uppercase",
            }}>
              Anomaly Detection
            </div>
          </div>
        </div>
      </div>

      {/* ── Navigation ──────────────────────────────────── */}
      <nav style={{ flex: 1, padding: "14px 10px 10px", overflowY: "auto", scrollbarWidth: "none" }}>
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.2em",
          color: "rgba(61,90,128,0.55)", textTransform: "uppercase",
          padding: "0 8px 10px",
        }}>
          Navigation
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          {NAV_ITEMS.map(({ href, label, sublabel, icon: Icon, shortcut }, idx) => {
            const isActive = pathname === href || (href !== "/" && pathname.startsWith(href));

            return (
              <Link
                key={href}
                href={href}
                style={{ textDecoration: "none", display: "block", position: "relative" }}
              >
                {/* Active bg fill */}
                {isActive && (
                  <motion.div
                    layoutId="nav-active-bg"
                    style={{
                      position: "absolute", inset: 0, borderRadius: "9px",
                      background: "rgba(34,211,238,0.07)",
                      border: "1px solid rgba(34,211,238,0.14)",
                      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
                    }}
                    transition={{ type: "spring", stiffness: 380, damping: 36 }}
                  />
                )}

                <div
                  style={{
                    display: "flex", alignItems: "center", gap: "10px",
                    padding: "9px 10px",
                    borderRadius: "9px",
                    position: "relative",
                    transition: "background 0.15s ease",
                    cursor: "pointer",
                  }}
                  onMouseEnter={e => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.025)";
                  }}
                  onMouseLeave={e => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
                  }}
                >
                  {/* Active left rule */}
                  {isActive && (
                    <motion.div
                      layoutId="nav-active-rule"
                      style={{
                        position: "absolute", left: 0, top: "22%", bottom: "22%",
                        width: "2.5px", borderRadius: "0 3px 3px 0",
                        background: "linear-gradient(180deg, #22D3EE 0%, #3B82F6 100%)",
                        boxShadow: "0 0 10px rgba(34,211,238,0.7)",
                      }}
                      transition={{ type: "spring", stiffness: 380, damping: 36 }}
                    />
                  )}

                  {/* Icon cell */}
                  <div style={{
                    width: "32px", height: "32px", borderRadius: "8px", flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    transition: "all 0.2s ease",
                    background: isActive
                      ? "linear-gradient(135deg, rgba(34,211,238,0.16) 0%, rgba(59,130,246,0.12) 100%)"
                      : "rgba(28,45,68,0.35)",
                    border: isActive
                      ? "1px solid rgba(34,211,238,0.22)"
                      : "1px solid rgba(28,45,68,0.5)",
                    boxShadow: isActive ? "0 0 12px rgba(34,211,238,0.15)" : "none",
                  }}>
                    <Icon
                      size={14}
                      strokeWidth={isActive ? 2 : 1.5}
                      color={isActive ? "#22D3EE" : "#3D5A80"}
                      style={{ filter: isActive ? "drop-shadow(0 0 5px rgba(34,211,238,0.55))" : "none", transition: "all 0.2s ease" }}
                    />
                  </div>

                  {/* Text */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontFamily: "var(--font-jakarta)",
                      fontSize: "13px",
                      fontWeight: isActive ? 650 : 500,
                      color: isActive ? "#EAF2FF" : "#5C7A9B",
                      lineHeight: 1.2,
                      transition: "color 0.15s ease",
                      letterSpacing: "-0.01em",
                    }}>
                      {label}
                    </div>
                    <AnimatePresence>
                      {isActive && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.18 }}
                          style={{
                            fontFamily: "var(--font-mono)", fontSize: "9px",
                            color: "rgba(34,211,238,0.45)", textTransform: "uppercase",
                            letterSpacing: "0.1em", marginTop: "2px", overflow: "hidden",
                          }}
                        >
                          {sublabel}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* Shortcut chip — only on active */}
                  <AnimatePresence>
                    {isActive && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        style={{
                          fontFamily: "var(--font-mono)", fontSize: "8px",
                          color: "rgba(34,211,238,0.3)", letterSpacing: "0.04em",
                          flexShrink: 0,
                        }}
                      >
                        {shortcut}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </Link>
            );
          })}
        </div>
      </nav>

      {/* ── Divider ──────────────────────────────────────── */}
      <div style={{ margin: "0 14px", height: "1px", background: "rgba(28,45,68,0.5)" }} />

      {/* ── Status footer ────────────────────────────────── */}
      <div style={{ padding: "14px 18px 18px" }}>
        {/* Live indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: "7px", marginBottom: "10px" }}>
          <div style={{ position: "relative", width: "8px", height: "8px", flexShrink: 0 }}>
            {/* Ping ring */}
            <div style={{
              position: "absolute", inset: "-3px",
              borderRadius: "50%", border: "1px solid rgba(16,185,129,0.35)",
              animation: "status-ping 2.5s ease-out infinite",
            }} />
            <div style={{
              width: "8px", height: "8px", borderRadius: "50%",
              background: "#10B981",
              boxShadow: "0 0 8px rgba(16,185,129,0.8)",
            }} />
          </div>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "9px",
            letterSpacing: "0.15em", color: "#10B981", textTransform: "uppercase",
          }}>
            System Online
          </span>
        </div>

        {/* Metadata */}
        <div style={{
          display: "flex", alignItems: "center", gap: "6px",
          fontFamily: "var(--font-mono)", fontSize: "8px",
          color: "rgba(61,90,128,0.45)", letterSpacing: "0.1em", textTransform: "uppercase",
        }}>
          <Zap size={9} color="rgba(61,90,128,0.4)" />
          v1.0 · Production
        </div>
      </div>

      {/* Bottom ambient line */}
      <div style={{
        position: "absolute", bottom: 0, left: 0, right: 0, height: "1px",
        background: "linear-gradient(90deg, transparent, rgba(59,130,246,0.2), transparent)",
      }} />

      <style>{`
        @keyframes logo-sweep {
          0%, 100% { transform: translateX(-200%); opacity: 0; }
          30% { opacity: 1; }
          60% { transform: translateX(200%); opacity: 0; }
        }
        @keyframes status-ping {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.5); opacity: 0; }
        }
      `}</style>
    </aside>
  );
}

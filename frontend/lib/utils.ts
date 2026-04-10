import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format seconds → "1:23" or "0:45" */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Format ISO date string → "Jan 15, 2025 · 14:32" */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    + " · "
    + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Short date "Jan 15" */
export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Score → grade color class */
export function gradeColor(grade: string | null | undefined): string {
  switch (grade?.toUpperCase()) {
    case "A": return "text-emerald-400";
    case "B": return "text-blue-400";
    case "C": return "text-amber-400";
    case "D": return "text-orange-400";
    case "F": return "text-red-400";
    default:  return "text-ink-secondary";
  }
}

/** Score → hex color */
export function scoreToColor(score: number): string {
  if (score >= 90) return "#10B981";
  if (score >= 80) return "#3B82F6";
  if (score >= 70) return "#F59E0B";
  if (score >= 60) return "#F97316";
  return "#EF4444";
}

/** Anomaly type → human-readable label */
export function anomalyLabel(type: string): string {
  const labels: Record<string, string> = {
    hard_braking:           "Hard Braking",
    near_miss:              "Near Miss",
    lane_departure:         "Lane Departure",
    traffic_violation:      "Traffic Violation",
    tailgating:             "Tailgating",
    aggressive_lane_change: "Aggressive Lane Change",
    harsh_cornering:        "Harsh Cornering",
    other:                  "Other",
  };
  return labels[type] ?? type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

/** Anomaly type → CSS badge class */
export function anomalyBadgeClass(type: string): string {
  const map: Record<string, string> = {
    hard_braking:           "badge-hard-braking",
    near_miss:              "badge-near-miss",
    lane_departure:         "badge-lane-departure",
    traffic_violation:      "badge-traffic-violation",
    tailgating:             "badge-tailgating",
    aggressive_lane_change: "badge-aggressive-lane-change",
    harsh_cornering:        "badge-harsh-cornering",
  };
  return map[type] ?? "badge-other";
}

/** Status → color class */
export function statusColor(status: string): string {
  switch (status) {
    case "done":       return "text-emerald-400";
    case "pending":    return "text-amber-400";
    case "processing": return "text-blue-400";
    case "error":      return "text-red-400";
    default:           return "text-ink-secondary";
  }
}

/** Severity 0–1 → visual bar width % */
export function severityPercent(severity: number): number {
  return Math.round(Math.max(0, Math.min(1, severity)) * 100);
}

/** Severity 0–1 → color */
export function severityColor(severity: number): string {
  if (severity >= 0.8) return "#EF4444";
  if (severity >= 0.6) return "#F97316";
  if (severity >= 0.4) return "#F59E0B";
  return "#10B981";
}

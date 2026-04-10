"use client";

import { severityColor, severityPercent, cn } from "@/lib/utils";

interface SeverityBarProps {
  severity: number;
  className?: string;
  showLabel?: boolean;
}

export function SeverityBar({ severity, className, showLabel = true }: SeverityBarProps) {
  const pct = severityPercent(severity);
  const color = severityColor(severity);

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className="relative flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ background: "rgba(28,45,68,0.8)" }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color, boxShadow: `0 0 6px ${color}60` }}
        />
      </div>
      {showLabel && (
        <span
          className="font-mono text-[10px] w-8 text-right tabular-nums flex-shrink-0"
          style={{ color }}
        >
          {pct}%
        </span>
      )}
    </div>
  );
}

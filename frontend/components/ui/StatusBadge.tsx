import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const STATUS_CONFIG: Record<string, { label: string; dot: string; color: string }> = {
  done:       { label: "Done",       dot: "#10B981", color: "#10B981" },
  pending:    { label: "Pending",    dot: "#F59E0B", color: "#F59E0B" },
  processing: { label: "Processing", dot: "#3B82F6", color: "#3B82F6" },
  error:      { label: "Error",      dot: "#F43F5E", color: "#F43F5E" },
  queued:     { label: "Queued",     dot: "#F59E0B", color: "#F59E0B" },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? {
    label: status, dot: "var(--color-muted)", color: "var(--color-ink-tertiary)",
  };
  const isPulse = ["pending", "processing", "queued"].includes(status);

  return (
    <span
      className={cn("inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest", className)}
      style={{ color: config.color }}
    >
      <span
        className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", isPulse && "animate-pulse-soft")}
        style={{ background: config.dot, boxShadow: `0 0 4px ${config.dot}80` }}
      />
      {config.label}
    </span>
  );
}

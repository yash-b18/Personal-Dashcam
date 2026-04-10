import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const STATUS_CONFIG: Record<string, { label: string; dot: string; text: string }> = {
  done:       { label: "Done",       dot: "bg-emerald-400", text: "text-emerald-400" },
  pending:    { label: "Pending",    dot: "bg-amber-400 animate-pulse", text: "text-amber-400" },
  processing: { label: "Processing", dot: "bg-blue-400 animate-pulse",  text: "text-blue-400"  },
  error:      { label: "Error",      dot: "bg-red-400",     text: "text-red-400"    },
  queued:     { label: "Queued",     dot: "bg-amber-400 animate-pulse", text: "text-amber-400" },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    dot: "bg-ink-tertiary",
    text: "text-ink-secondary",
  };

  return (
    <span className={cn("inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest", config.text, className)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", config.dot)} />
      {config.label}
    </span>
  );
}

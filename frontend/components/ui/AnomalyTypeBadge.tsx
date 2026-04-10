import { anomalyLabel, anomalyBadgeClass, cn } from "@/lib/utils";

interface AnomalyTypeBadgeProps {
  type: string;
  className?: string;
  size?: "sm" | "md";
}

export function AnomalyTypeBadge({ type, className, size = "md" }: AnomalyTypeBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center font-mono border rounded-sm",
        size === "sm" ? "text-[9px] px-1.5 py-0.5 tracking-wider" : "text-[10px] px-2 py-1 tracking-widest",
        "uppercase font-medium",
        anomalyBadgeClass(type),
        className
      )}
    >
      {anomalyLabel(type)}
    </span>
  );
}

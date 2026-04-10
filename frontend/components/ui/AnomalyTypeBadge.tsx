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
        "inline-flex items-center font-mono border",
        size === "sm"
          ? "text-[9px] px-1.5 py-0.5 tracking-wider rounded"
          : "text-[10px] px-2.5 py-1 tracking-widest rounded-badge",
        "uppercase font-semibold",
        anomalyBadgeClass(type),
        className
      )}
    >
      {anomalyLabel(type)}
    </span>
  );
}

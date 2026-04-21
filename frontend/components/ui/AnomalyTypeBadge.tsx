import { anomalyLabel, anomalyBadgeClass, cn } from "@/lib/utils";

interface AnomalyTypeBadgeProps {
  type: string;
  className?: string;
  size?: "sm" | "md";
}

// Block-level pill with `width: fit-content` + `max-width: 100%` so it sizes to
// its text but caps at the parent's inner width. Long labels like
// "AGGRESSIVE LANE CHANGE" wrap onto a second line instead of being clipped by
// ancestor `overflow-hidden` or narrow 4-col card grids.
export function AnomalyTypeBadge({ type, className, size = "md" }: AnomalyTypeBadgeProps) {
  const isSm = size === "sm";
  return (
    <span
      className={cn(
        "font-mono border uppercase font-semibold",
        isSm
          ? "text-[9px] px-1.5 py-0.5 rounded"
          : "text-[10px] px-2.5 py-1 rounded-badge",
        anomalyBadgeClass(type),
        className,
      )}
      style={{
        display: "block",
        width: "fit-content",
        maxWidth: "100%",
        letterSpacing: isSm ? "0.04em" : "0.08em",
        whiteSpace: "normal",
        wordBreak: "break-word",
        overflowWrap: "anywhere",
        lineHeight: 1.35,
      }}
    >
      {anomalyLabel(type)}
    </span>
  );
}

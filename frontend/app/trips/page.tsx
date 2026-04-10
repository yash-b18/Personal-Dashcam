"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Film, ChevronLeft, ChevronRight, Play, RefreshCw } from "lucide-react";

import { api, ClipSummary } from "@/lib/api";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatDuration, scoreToColor, cn } from "@/lib/utils";

const PAGE_SIZE = 30;
const STATUS_OPTIONS = ["", "done", "pending", "processing", "error"];

function ScorePill({ score, grade }: { score: number | null; grade: string | null }) {
  if (score == null) return <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>—</span>;
  const color = scoreToColor(score);
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-display" style={{ fontSize: "1.25rem", lineHeight: 1, color }}>{Math.round(score)}</span>
      {grade && <span className="font-mono text-[10px] font-semibold" style={{ color }}>{grade}</span>}
    </div>
  );
}

function ClipRow({ clip, index, onProcess }: { clip: ClipSummary; index: number; onProcess: (id: string) => void }) {
  const [processing, setProcessing] = useState(false);
  const handleProcess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (clip.processing_status === "processing") return;
    setProcessing(true);
    try { await onProcess(clip.id); } finally { setProcessing(false); }
  };

  return (
    <motion.tr
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.018, duration: 0.3 }}
      className="row-hover group"
      style={{ borderBottom: "1px solid var(--color-border)" }}
    >
      <td className="py-3 pl-5 pr-3 w-14">
        <div className="w-11 h-8 rounded-lg flex items-center justify-center overflow-hidden flex-shrink-0"
             style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
          {clip.front_url
            ? <video src={clip.front_url} className="w-full h-full object-cover" muted preload="none" />
            : <Film size={11} style={{ color: "var(--color-ink-tertiary)" }} />}
        </div>
      </td>
      <td className="py-3 pr-4">
        <div className="text-[12px] font-medium truncate max-w-[200px]" style={{ color: "var(--color-ink-primary)" }}>{clip.filename_prefix}</div>
        <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>{formatDate(clip.recorded_at)}</div>
      </td>
      <td className="py-3 pr-4 font-mono text-[11px] whitespace-nowrap" style={{ color: "var(--color-ink-secondary)" }}>
        {formatDuration(clip.duration_seconds)}
      </td>
      <td className="py-3 pr-4"><StatusBadge status={clip.processing_status} /></td>
      <td className="py-3 pr-4"><ScorePill score={clip.score} grade={clip.grade} /></td>
      <td className="py-3 pr-4 font-mono text-[11px]">
        {clip.anomaly_count > 0
          ? <span style={{ color: clip.anomaly_count > 5 ? "#F43F5E" : "#F59E0B" }}>{clip.anomaly_count}</span>
          : <span style={{ color: "var(--color-ink-tertiary)" }}>0</span>}
      </td>
      <td className="py-3 pr-4">
        <button
          onClick={handleProcess}
          disabled={processing || clip.processing_status === "processing"}
          className={cn(
            "w-7 h-7 flex items-center justify-center rounded-lg border transition-all duration-200",
            "opacity-0 group-hover:opacity-100",
            processing || clip.processing_status === "processing"
              ? "cursor-not-allowed"
              : "hover:bg-accent/10"
          )}
          style={{
            border: processing ? "1px solid var(--color-border)" : "1px solid rgba(34,211,238,0.3)",
            color: processing ? "var(--color-ink-tertiary)" : "var(--color-accent)",
          }}
        >
          <Play size={10} className={processing ? "animate-pulse" : ""} />
        </button>
      </td>
    </motion.tr>
  );
}

export default function TripsPage() {
  const [clips, setClips] = useState<ClipSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [processAllLoading, setProcessAllLoading] = useState(false);

  const fetchClips = useCallback(() => {
    setLoading(true);
    api.clips.list({ page, page_size: PAGE_SIZE, status: statusFilter || undefined })
      .then(d => { setClips(d.clips); setTotal(d.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, statusFilter]);

  useEffect(() => { fetchClips(); }, [fetchClips]);
  useEffect(() => { setPage(1); }, [statusFilter]);

  const handleProcess = async (id: string) => { await api.clips.process(id); fetchClips(); };
  const handleProcessAll = async () => {
    setProcessAllLoading(true);
    try { await api.clips.processAll(); fetchClips(); } finally { setProcessAllLoading(false); }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6">
        <p className="section-label mb-2">Data Management</p>
        <div className="flex items-end justify-between">
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>Video Library</h1>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>{total} clips</span>
            <button onClick={handleProcessAll} disabled={processAllLoading} className="btn-primary disabled:opacity-50" style={{ fontSize: "12px", padding: "7px 14px" }}>
              <RefreshCw size={12} className={processAllLoading ? "animate-spin" : ""} />
              Process All
            </button>
          </div>
        </div>
      </motion.div>

      {/* Status filter */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} className="panel p-4 mb-5">
        <div className="flex gap-2 items-center flex-wrap">
          <p className="section-label mr-1">Status</p>
          {STATUS_OPTIONS.map(s => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              className="font-mono text-[10px] uppercase px-3 py-1.5 rounded-lg border transition-all"
              style={{
                borderColor: statusFilter === s ? "var(--color-accent)" : "var(--color-border)",
                background: statusFilter === s ? "rgba(34,211,238,0.1)" : "transparent",
                color: statusFilter === s ? "var(--color-accent)" : "var(--color-ink-tertiary)",
              }}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Table */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }} className="panel overflow-hidden">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border)", background: "rgba(12,25,40,0.6)" }}>
              {["Clip", "Filename / Date", "Duration", "Status", "Score", "Anomalies", "Action"].map(h => (
                <th key={h} className="py-3 pl-4 text-left section-label" style={{ paddingLeft: h === "Clip" ? "20px" : "16px" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td className="py-3 pl-5 pr-3"><Skeleton className="w-11 h-8" /></td>
                    <td className="py-3 pr-4"><Skeleton className="h-3 w-36" /></td>
                    <td className="py-3 pr-4"><Skeleton className="h-3 w-12" /></td>
                    <td className="py-3 pr-4"><Skeleton className="h-3 w-20" /></td>
                    <td className="py-3 pr-4"><Skeleton className="h-5 w-10" /></td>
                    <td className="py-3 pr-4"><Skeleton className="h-3 w-6" /></td>
                    <td className="py-3 pr-4" />
                  </tr>
                ))
              : clips.length === 0
              ? (
                <tr><td colSpan={7} className="py-16 text-center">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3" style={{ background: "rgba(122,156,192,0.08)", border: "1px solid var(--color-border)" }}>
                    <Film size={20} style={{ color: "var(--color-ink-tertiary)" }} />
                  </div>
                  <p className="section-label mb-1.5">No clips found</p>
                  <p className="text-[12px]" style={{ color: "var(--color-ink-secondary)" }}>Ingest clips from R2 to get started.</p>
                </td></tr>
              )
              : clips.map((clip, i) => <ClipRow key={clip.id} clip={clip} index={i} onProcess={handleProcess} />)
            }
          </tbody>
        </table>
      </motion.div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>{page} / {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

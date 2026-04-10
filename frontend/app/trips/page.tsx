"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Film, ChevronLeft, ChevronRight, Play, RefreshCw } from "lucide-react";

import { api, ClipSummary } from "@/lib/api";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatDuration, scoreToColor, gradeColor, cn } from "@/lib/utils";

const PAGE_SIZE = 30;

const STATUS_OPTIONS = ["", "done", "pending", "processing", "error"];

// ── Score pill ────────────────────────────────────────────────────────────────
function ScorePill({ score, grade }: { score: number | null; grade: string | null }) {
  if (score == null) return <span className="font-mono text-[10px] text-ink-tertiary">—</span>;
  const color = scoreToColor(score);
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-display text-xl font-bold leading-none" style={{ fontFamily: "'Barlow Condensed'", color, fontWeight: 800 }}>
        {Math.round(score)}
      </span>
      {grade && (
        <span className="font-mono text-[10px] font-semibold" style={{ color }}>{grade}</span>
      )}
    </div>
  );
}

// ── Clip row ──────────────────────────────────────────────────────────────────
function ClipRow({ clip, index, onProcess }: { clip: ClipSummary; index: number; onProcess: (id: string) => void }) {
  const [processing, setProcessing] = useState(false);

  const handleProcess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (clip.processing_status === "processing") return;
    setProcessing(true);
    try {
      await onProcess(clip.id);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <motion.tr
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.02, duration: 0.3 }}
      className="border-b border-border row-hover group"
    >
      {/* Thumbnail cell */}
      <td className="py-3 pl-4 pr-3 w-16">
        <div className="w-12 h-8 bg-surface border border-border rounded-sm flex items-center justify-center overflow-hidden">
          {clip.front_url ? (
            <video
              src={clip.front_url}
              className="w-full h-full object-cover"
              muted
              preload="none"
            />
          ) : (
            <Film size={12} className="text-ink-tertiary" />
          )}
        </div>
      </td>

      {/* Filename */}
      <td className="py-3 pr-4">
        <div className="font-mono text-[11px] text-ink-primary truncate max-w-[200px]">{clip.filename_prefix}</div>
        <div className="font-mono text-[9px] text-ink-tertiary mt-0.5">{formatDate(clip.recorded_at)}</div>
      </td>

      {/* Duration */}
      <td className="py-3 pr-4 font-mono text-[11px] text-ink-secondary whitespace-nowrap">
        {formatDuration(clip.duration_seconds)}
      </td>

      {/* Status */}
      <td className="py-3 pr-4">
        <StatusBadge status={clip.processing_status} />
      </td>

      {/* Score */}
      <td className="py-3 pr-4">
        <ScorePill score={clip.score} grade={clip.grade} />
      </td>

      {/* Anomaly count */}
      <td className="py-3 pr-4 font-mono text-[11px] text-ink-secondary">
        {clip.anomaly_count > 0 ? (
          <span style={{ color: clip.anomaly_count > 5 ? "#EF4444" : "#F59E0B" }}>
            {clip.anomaly_count}
          </span>
        ) : (
          <span className="text-ink-tertiary">0</span>
        )}
      </td>

      {/* Actions */}
      <td className="py-3 pr-4">
        <button
          onClick={handleProcess}
          disabled={processing || clip.processing_status === "processing"}
          title="Process clip"
          className={cn(
            "w-7 h-7 flex items-center justify-center rounded-sm border transition-all duration-200",
            "opacity-0 group-hover:opacity-100",
            processing || clip.processing_status === "processing"
              ? "border-border text-ink-tertiary cursor-not-allowed"
              : "border-amber-dim text-amber-DEFAULT hover:bg-amber-subtle hover:border-amber-DEFAULT"
          )}
        >
          <Play size={10} className={processing ? "animate-pulse" : ""} />
        </button>
      </td>
    </motion.tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
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

  const handleProcess = async (id: string) => {
    await api.clips.process(id);
    fetchClips();
  };

  const handleProcessAll = async () => {
    setProcessAllLoading(true);
    try {
      await api.clips.processAll();
      fetchClips();
    } finally {
      setProcessAllLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6">
        <p className="section-label mb-1">DATA MANAGEMENT</p>
        <div className="flex items-end justify-between">
          <h1 className="font-display text-4xl font-extrabold tracking-wide"
              style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 900, fontSize: "2.5rem", letterSpacing: "0.04em" }}>
            VIDEO LIBRARY
          </h1>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] text-ink-tertiary">{total} clips total</span>
            <button
              onClick={handleProcessAll}
              disabled={processAllLoading}
              className="flex items-center gap-2 px-4 py-2 bg-amber-subtle border border-amber-dim text-amber-DEFAULT font-mono text-[11px] rounded-sm hover:bg-amber-DEFAULT hover:text-void transition-all duration-200 disabled:opacity-50"
            >
              <RefreshCw size={12} className={processAllLoading ? "animate-spin" : ""} />
              PROCESS ALL
            </button>
          </div>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
        className="panel p-4 mb-5 flex gap-3 items-center"
      >
        <p className="section-label text-ink-secondary">STATUS</p>
        <div className="flex gap-2 flex-wrap">
          {STATUS_OPTIONS.map(s => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "font-mono text-[10px] uppercase px-3 py-1 rounded-sm border transition-all",
                statusFilter === s
                  ? "border-amber-DEFAULT bg-amber-subtle text-amber-DEFAULT"
                  : "border-border text-ink-tertiary hover:border-muted hover:text-ink-secondary"
              )}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
        className="panel overflow-hidden"
      >
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-surface">
              <th className="py-3 pl-4 pr-3 text-left section-label">CLIP</th>
              <th className="py-3 pr-4 text-left section-label">FILENAME / DATE</th>
              <th className="py-3 pr-4 text-left section-label">DURATION</th>
              <th className="py-3 pr-4 text-left section-label">STATUS</th>
              <th className="py-3 pr-4 text-left section-label">SCORE</th>
              <th className="py-3 pr-4 text-left section-label">ANOMALIES</th>
              <th className="py-3 pr-4 text-left section-label">ACTION</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-border">
                    <td className="py-3 pl-4 pr-3"><Skeleton className="w-12 h-8" /></td>
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
                <tr>
                  <td colSpan={7} className="py-16 text-center">
                    <Film size={32} className="text-ink-tertiary mx-auto mb-3" />
                    <p className="section-label mb-1">NO CLIPS FOUND</p>
                    <p className="text-data text-ink-secondary">Ingest clips from R2 with the data pipeline.</p>
                  </td>
                </tr>
              )
              : clips.map((clip, i) => (
                  <ClipRow key={clip.id} clip={clip} index={i} onProcess={handleProcess} />
                ))
            }
          </tbody>
        </table>
      </motion.div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30 hover:border-amber-dim transition-colors"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[11px] text-ink-secondary">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30 hover:border-amber-dim transition-colors"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

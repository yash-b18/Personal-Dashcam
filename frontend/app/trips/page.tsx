"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Film, ChevronLeft, ChevronRight, Play, RefreshCw, Eye, Upload, Search, X,
} from "lucide-react";

import { api, ClipSummary } from "@/lib/api";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ClipReviewModal } from "@/components/ui/ClipReviewModal";
import { UploadModal } from "@/components/ui/UploadModal";
import { VideoThumbnail } from "@/components/ui/VideoThumbnail";
import { formatDate, formatDuration, scoreToColor, cn } from "@/lib/utils";

const PAGE_SIZE_OPTIONS = [10, 20, 30] as const;
const STATUS_OPTIONS = ["", "done", "pending", "processing", "error"];

// Column widths — keeps header + body cells perfectly aligned.
// Kept tight so the table doesn't sprawl on wide monitors.
const COLS = [
  { key: "clip",     width: "56px",  label: "Clip",         align: "left"  as const },
  { key: "name",     width: "auto",  label: "Filename / Date", align: "left" as const },
  { key: "duration", width: "70px",  label: "Dur",          align: "left"  as const },
  { key: "status",   width: "110px", label: "Status",       align: "left"  as const },
  { key: "score",    width: "90px",  label: "Score",        align: "left"  as const },
  { key: "anoms",    width: "78px",  label: "Anoms",        align: "left"  as const },
  { key: "action",   width: "100px", label: "Action",       align: "right" as const },
];

// ── Small sub-components ────────────────────────────────────────────────

function ScorePill({ score, grade }: { score: number | null; grade: string | null }) {
  if (score == null) return <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>—</span>;
  const color = scoreToColor(score);
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-display" style={{ fontSize: "1.1rem", lineHeight: 1, color }}>{Math.round(score)}</span>
      {grade && <span className="font-mono text-[9px] font-semibold" style={{ color }}>{grade}</span>}
    </div>
  );
}

function Metric({ label, value, tone = "ink", accent }: {
  label: string; value: string | number; tone?: "ink" | "warn" | "ok" | "bad" | "accent"; accent?: boolean;
}) {
  const color =
    tone === "warn"   ? "#F59E0B"
    : tone === "ok"   ? "#10B981"
    : tone === "bad"  ? "#F43F5E"
    : tone === "accent" ? "var(--color-accent)"
    : "var(--color-ink-primary)";
  return (
    <div
      className="flex items-baseline gap-2 px-3 py-1.5 rounded-md"
      style={{
        background: accent ? "rgba(34,211,238,0.05)" : "transparent",
        border: accent ? "1px solid rgba(34,211,238,0.18)" : "1px solid transparent",
      }}
    >
      <span className="text-display tabular-nums" style={{ fontSize: "1rem", lineHeight: 1, color }}>{value}</span>
      <span className="font-mono text-[9px] uppercase tracking-[0.16em]" style={{ color: "var(--color-ink-tertiary)" }}>
        {label}
      </span>
    </div>
  );
}

function FilterChip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-md border transition-all tracking-[0.12em]"
      style={{
        borderColor: active ? "var(--color-accent)" : "var(--color-border)",
        background: active ? "rgba(34,211,238,0.1)" : "transparent",
        color: active ? "var(--color-accent)" : "var(--color-ink-tertiary)",
      }}
    >
      {label}
    </button>
  );
}

function ClipRow({
  clip, index, onView, onProcess,
}: {
  clip: ClipSummary;
  index: number;
  onView: (id: string) => void;
  onProcess: (id: string) => void;
}) {
  const [reprocessing, setReprocessing] = useState(false);
  const handleReprocess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (clip.processing_status === "processing") return;
    setReprocessing(true);
    try { await onProcess(clip.id); } finally { setReprocessing(false); }
  };

  return (
    <motion.tr
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.015, duration: 0.26 }}
      onClick={() => onView(clip.id)}
      className="row-hover group cursor-pointer"
      style={{ borderBottom: "1px solid var(--color-border)" }}
    >
      {/* Thumbnail */}
      <td className="py-2 pl-5 pr-2 align-middle">
        <div
          className="relative w-10 h-7 rounded-md overflow-hidden flex items-center justify-center"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
        >
          {clip.front_url
            ? <VideoThumbnail
                src={clip.front_url}
                seekTo={Math.min(0.5, (clip.duration_seconds ?? 1) * 0.1)}
                className="w-full h-full object-cover"
              />
            : <Film size={10} style={{ color: "var(--color-ink-tertiary)" }} />}
          <div
            className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200"
            style={{ background: "rgba(4,10,20,0.55)" }}
          >
            <Play size={11} style={{ color: "var(--color-accent)", filter: "drop-shadow(0 0 4px rgba(34,211,238,0.6))" }} />
          </div>
        </div>
      </td>

      {/* Filename / Date */}
      <td className="py-2 px-3 align-middle">
        <div className="text-[12px] font-medium truncate" style={{ color: "var(--color-ink-primary)" }}>{clip.filename_prefix}</div>
        <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>{formatDate(clip.recorded_at)}</div>
      </td>

      {/* Duration */}
      <td className="py-2 px-3 align-middle font-mono text-[11px] whitespace-nowrap tabular-nums" style={{ color: "var(--color-ink-secondary)" }}>
        {formatDuration(clip.duration_seconds)}
      </td>

      {/* Status */}
      <td className="py-2 px-3 align-middle"><StatusBadge status={clip.processing_status} /></td>

      {/* Score */}
      <td className="py-2 px-3 align-middle"><ScorePill score={clip.score} grade={clip.grade} /></td>

      {/* Anomalies */}
      <td className="py-2 px-3 align-middle font-mono text-[11px] tabular-nums">
        {clip.anomaly_count > 0
          ? <span style={{ color: clip.anomaly_count > 5 ? "#F43F5E" : "#F59E0B" }}>{clip.anomaly_count}</span>
          : <span style={{ color: "var(--color-ink-tertiary)" }}>0</span>}
      </td>

      {/* Action */}
      <td className="py-2 pl-3 pr-5 align-middle">
        <div className="flex items-center justify-end gap-1.5">
          <button
            onClick={handleReprocess}
            disabled={reprocessing || clip.processing_status === "processing"}
            aria-label="Re-process clip"
            className={cn(
              "w-6 h-6 flex items-center justify-center rounded-md border transition-all",
              "opacity-0 group-hover:opacity-100",
              reprocessing || clip.processing_status === "processing" ? "cursor-not-allowed" : "hover:bg-accent/10",
            )}
            style={{
              borderColor: "var(--color-border)",
              color: reprocessing || clip.processing_status === "processing"
                ? "var(--color-ink-tertiary)"
                : "var(--color-ink-secondary)",
            }}
          >
            <RefreshCw size={9} className={reprocessing || clip.processing_status === "processing" ? "animate-spin" : ""} />
          </button>

          <button
            onClick={(e) => { e.stopPropagation(); onView(clip.id); }}
            className="flex items-center gap-1 px-2 py-1 rounded-md border transition-all font-mono text-[9px] uppercase tracking-[0.14em]"
            style={{
              borderColor: "rgba(34,211,238,0.25)",
              background: "rgba(34,211,238,0.05)",
              color: "var(--color-accent)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(34,211,238,0.14)";
              e.currentTarget.style.borderColor = "rgba(34,211,238,0.5)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "rgba(34,211,238,0.05)";
              e.currentTarget.style.borderColor = "rgba(34,211,238,0.25)";
            }}
          >
            <Eye size={10} /> View
          </button>
        </div>
      </td>
    </motion.tr>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────

export default function TripsPage() {
  const [clips, setClips] = useState<ClipSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(30);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [processAllLoading, setProcessAllLoading] = useState(false);
  const [reprocessAllLoading, setReprocessAllLoading] = useState(false);
  const [reprocessConfirmOpen, setReprocessConfirmOpen] = useState(false);
  const [toast, setToast] = useState<{ kind: "info" | "success" | "warn"; text: string } | null>(null);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const fetchClips = useCallback((opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    api.clips.list({ page, page_size: pageSize, status: statusFilter || undefined })
      .then(d => { setClips(d.clips); setTotal(d.total); })
      .catch(() => {})
      .finally(() => { if (!opts?.silent) setLoading(false); });
  }, [page, pageSize, statusFilter]);

  useEffect(() => { fetchClips(); }, [fetchClips]);
  useEffect(() => { setPage(1); }, [statusFilter, pageSize]);

  // Poll while any clip on this page is processing so status badges update live.
  // Use `silent` so the table doesn't flash its loading skeleton every tick.
  const hasProcessing = clips.some(c => c.processing_status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const id = setInterval(() => fetchClips({ silent: true }), 5000);
    return () => clearInterval(id);
  }, [hasProcessing, fetchClips]);

  const showToast = (kind: "info" | "success" | "warn", text: string) => {
    setToast({ kind, text });
    setTimeout(() => setToast(null), 4500);
  };

  const handleProcess = async (id: string) => { await api.clips.process(id); fetchClips(); };
  const handleProcessAll = async () => {
    setProcessAllLoading(true);
    try {
      const res = await api.clips.processAll();
      if (res.enqueued === 0) {
        showToast("info", "No pending clips to process.");
      } else {
        showToast("success", `Enqueued ${res.enqueued} pending clip${res.enqueued === 1 ? "" : "s"}.`);
      }
      fetchClips();
    } catch {
      showToast("warn", "Process-all request failed.");
    } finally {
      setProcessAllLoading(false);
    }
  };
  const handleReprocessAll = async () => {
    setReprocessConfirmOpen(false);
    setReprocessAllLoading(true);
    try {
      const res = await api.clips.reprocessAll();
      showToast("success", `Reprocessing ${res.enqueued} clip${res.enqueued === 1 ? "" : "s"} — this will take a while.`);
      fetchClips();
    } catch {
      showToast("warn", "Reprocess-all request failed.");
    } finally {
      setReprocessAllLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Client-side filename search over the current page
  const visibleClips = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return clips;
    return clips.filter(c => c.filename_prefix.toLowerCase().includes(q));
  }, [clips, search]);

  // Page-scoped KPI counts (backend doesn't return totals per status on a single call)
  const kpis = useMemo(() => {
    const done = clips.filter(c => c.processing_status === "done").length;
    const pending = clips.filter(c => c.processing_status === "pending").length;
    const processing = clips.filter(c => c.processing_status === "processing").length;
    const errored = clips.filter(c => c.processing_status === "error").length;
    return { done, pending, processing, errored };
  }, [clips]);

  return (
    <div className="px-7 py-6 max-w-[1400px] mx-auto">
      {/* ── Compact header + inline stats strip ───────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32 }}
        className="flex items-end justify-between flex-wrap gap-4 mb-4"
      >
        <div className="min-w-0">
          <p className="section-label mb-1.5">Data Management</p>
          <div className="flex items-baseline gap-4 flex-wrap">
            <h1 className="text-display" style={{ fontSize: "1.75rem", letterSpacing: "-0.02em", lineHeight: 1 }}>
              Video Library
            </h1>
            <div className="flex items-center gap-1">
              <Metric label="Total" value={total} accent />
              <Metric label="Done" value={kpis.done} tone="ok" />
              <Metric label="Pending" value={kpis.pending} tone="warn" />
              {kpis.processing > 0 && <Metric label="Active" value={kpis.processing} tone="accent" />}
              {kpis.errored > 0 && <Metric label="Errors" value={kpis.errored} tone="bad" />}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all"
            style={{
              background: "rgba(34,211,238,0.14)",
              border: "1px solid rgba(34,211,238,0.4)",
              color: "var(--color-accent)",
              boxShadow: "0 0 20px rgba(34,211,238,0.08)",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(34,211,238,0.22)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(34,211,238,0.14)"; }}
          >
            <Upload size={11} /> Upload Clip
          </button>
          <button
            onClick={handleProcessAll}
            disabled={processAllLoading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all disabled:opacity-50"
            style={{
              background: "transparent",
              border: "1px solid var(--color-border)",
              color: "var(--color-ink-secondary)",
            }}
          >
            <RefreshCw size={11} className={processAllLoading ? "animate-spin" : ""} />
            Process All
          </button>
          <button
            onClick={() => setReprocessConfirmOpen(true)}
            disabled={reprocessAllLoading}
            title="Re-run the pipeline on every clip, even ones already DONE"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all disabled:opacity-50"
            style={{
              background: "rgba(245,158,11,0.06)",
              border: "1px solid rgba(245,158,11,0.35)",
              color: "#F59E0B",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(245,158,11,0.14)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(245,158,11,0.06)"; }}
          >
            <RefreshCw size={11} className={reprocessAllLoading ? "animate-spin" : ""} />
            Reprocess All
          </button>
        </div>
      </motion.div>

      {/* ── Toast ─────────────────────────────────────────────────────── */}
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          className="fixed top-6 right-6 z-50 px-4 py-3 rounded-lg font-mono text-[11px] tracking-[0.04em] shadow-2xl"
          style={{
            background:
              toast.kind === "success" ? "rgba(16,185,129,0.12)"
              : toast.kind === "warn" ? "rgba(244,63,94,0.12)"
              : "rgba(34,211,238,0.10)",
            border: `1px solid ${
              toast.kind === "success" ? "rgba(16,185,129,0.45)"
              : toast.kind === "warn" ? "rgba(244,63,94,0.45)"
              : "rgba(34,211,238,0.35)"
            }`,
            color:
              toast.kind === "success" ? "#6EE7B7"
              : toast.kind === "warn" ? "#FCA5A5"
              : "#67E8F9",
            backdropFilter: "blur(8px)",
          }}
          onClick={() => setToast(null)}
        >
          {toast.text}
        </motion.div>
      )}

      {/* ── Reprocess confirmation ───────────────────────────────────── */}
      {reprocessConfirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(4,10,20,0.7)", backdropFilter: "blur(6px)" }}
          onClick={() => setReprocessConfirmOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl p-6"
            style={{
              background: "linear-gradient(180deg,#0B1726,#091523)",
              border: "1px solid rgba(245,158,11,0.35)",
            }}
          >
            <p className="section-label mb-2" style={{ color: "#F59E0B" }}>
              Reprocess every clip?
            </p>
            <p className="text-[12px] leading-relaxed mb-5" style={{ color: "var(--color-ink-secondary)" }}>
              This re-runs the classical pipeline on every clip in the library
              (skipping only clips already in the processing queue). Existing
              anomalies and scores for those clips are overwritten. With 626
              clips this can take ~30–60 minutes.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setReprocessConfirmOpen(false)}
                className="px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em]"
                style={{ border: "1px solid var(--color-border)", color: "var(--color-ink-secondary)" }}
              >
                Cancel
              </button>
              <button
                onClick={handleReprocessAll}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em]"
                style={{
                  background: "rgba(245,158,11,0.14)",
                  border: "1px solid rgba(245,158,11,0.5)",
                  color: "#F59E0B",
                }}
              >
                <RefreshCw size={11} /> Reprocess All
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── Inline toolbar: filters + search ─────────────────────────── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.08 }}
        className="flex items-center gap-3 flex-wrap mb-3 pb-3"
        style={{ borderBottom: "1px solid var(--color-border)" }}
      >
        <span className="font-mono text-[9px] uppercase tracking-[0.2em]" style={{ color: "var(--color-ink-tertiary)" }}>
          Filter
        </span>
        <div className="flex items-center gap-1.5">
          {STATUS_OPTIONS.map(s => (
            <FilterChip
              key={s || "all"}
              label={s || "All"}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s)}
            />
          ))}
        </div>

        <div className="flex-1" />

        {/* Per-page selector */}
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[9px] uppercase tracking-[0.2em]" style={{ color: "var(--color-ink-tertiary)" }}>
            Per page
          </span>
          <div className="flex items-center gap-1">
            {PAGE_SIZE_OPTIONS.map(n => {
              const active = pageSize === n;
              return (
                <button
                  key={n}
                  onClick={() => setPageSize(n)}
                  className="font-mono text-[11px] px-2 py-1 rounded transition-colors"
                  style={
                    active
                      ? { background: "rgba(34,211,238,0.12)", border: "1px solid rgba(34,211,238,0.35)", color: "var(--color-accent)" }
                      : { background: "rgba(12,25,40,0.6)", border: "1px solid var(--color-border)", color: "var(--color-ink-secondary)" }
                  }
                >
                  {n}
                </button>
              );
            })}
          </div>
        </div>

        {/* Search */}
        <div
          className="relative flex items-center gap-2 px-2.5 py-1.5 rounded-md"
          style={{ background: "rgba(12,25,40,0.6)", border: "1px solid var(--color-border)", minWidth: 220 }}
        >
          <Search size={11} style={{ color: "var(--color-ink-tertiary)" }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search filename…"
            className="bg-transparent outline-none font-mono text-[11px] flex-1"
            style={{ color: "var(--color-ink-primary)" }}
          />
          {search && (
            <button onClick={() => setSearch("")} aria-label="Clear search" style={{ color: "var(--color-ink-tertiary)" }}>
              <X size={11} />
            </button>
          )}
        </div>
      </motion.div>

      {/* ── Table (dense, full width) ─────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.14 }}
        className="panel overflow-hidden"
      >
        <table className="w-full" style={{ tableLayout: "fixed" }}>
          <colgroup>
            {COLS.map(c => <col key={c.key} style={{ width: c.width }} />)}
          </colgroup>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border)", background: "rgba(12,25,40,0.6)" }}>
              {COLS.map((c, i) => (
                <th
                  key={c.key}
                  className="py-2.5 section-label"
                  style={{
                    textAlign: c.align,
                    paddingLeft: i === 0 ? "20px" : "12px",
                    paddingRight: i === COLS.length - 1 ? "20px" : "12px",
                    fontSize: "10px",
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td className="py-2 pl-5 pr-2"><Skeleton className="w-10 h-7" /></td>
                  <td className="py-2 px-3"><Skeleton className="h-3 w-40" /></td>
                  <td className="py-2 px-3"><Skeleton className="h-3 w-10" /></td>
                  <td className="py-2 px-3"><Skeleton className="h-3 w-18" /></td>
                  <td className="py-2 px-3"><Skeleton className="h-4 w-10" /></td>
                  <td className="py-2 px-3"><Skeleton className="h-3 w-5" /></td>
                  <td className="py-2 pl-3 pr-5"><div className="flex justify-end"><Skeleton className="h-5 w-14" /></div></td>
                </tr>
              ))
            ) : visibleClips.length === 0 ? (
              <tr>
                <td colSpan={COLS.length} className="py-14 text-center">
                  <div
                    className="w-11 h-11 rounded-xl flex items-center justify-center mx-auto mb-3"
                    style={{ background: "rgba(122,156,192,0.08)", border: "1px solid var(--color-border)" }}
                  >
                    <Film size={18} style={{ color: "var(--color-ink-tertiary)" }} />
                  </div>
                  <p className="section-label mb-1">{search ? "No matches" : "No clips found"}</p>
                  <p className="text-[12px]" style={{ color: "var(--color-ink-secondary)" }}>
                    {search ? `Nothing matching "${search}"` : "Upload a clip or ingest from R2 to get started."}
                  </p>
                  {!search && (
                    <button
                      onClick={() => setUploadOpen(true)}
                      className="mt-4 flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] mx-auto"
                      style={{
                        background: "rgba(34,211,238,0.14)",
                        border: "1px solid rgba(34,211,238,0.4)",
                        color: "var(--color-accent)",
                      }}
                    >
                      <Upload size={11} /> Upload your first clip
                    </button>
                  )}
                </td>
              </tr>
            ) : (
              visibleClips.map((clip, i) => (
                <ClipRow
                  key={clip.id}
                  clip={clip}
                  index={i}
                  onView={setSelectedClipId}
                  onProcess={handleProcess}
                />
              ))
            )}
          </tbody>
        </table>
      </motion.div>

      {/* ── Pagination ───────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="mt-5 flex items-center justify-center gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="w-7 h-7 flex items-center justify-center panel-sm disabled:opacity-30"
          >
            <ChevronLeft size={13} />
          </button>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="w-7 h-7 flex items-center justify-center panel-sm disabled:opacity-30"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      )}

      {/* Modals */}
      <ClipReviewModal
        clipId={selectedClipId}
        onClose={() => setSelectedClipId(null)}
        onReprocess={handleProcess}
      />
      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onComplete={() => fetchClips()}
      />
    </div>
  );
}

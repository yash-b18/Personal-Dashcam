"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ThumbsUp, ThumbsDown, SkipForward, ChevronLeft, ChevronRight,
  Play, Pause, RotateCcw, Tag, Undo2, CheckCircle, XCircle, Clock,
  Edit3,
} from "lucide-react";

import { api, LabelQueueItem, LabelSubmit } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { formatDuration, formatDate, anomalyLabel, cn } from "@/lib/utils";

const ANOMALY_TYPES = [
  { key: "hard_braking",           label: "Hard Braking" },
  { key: "near_miss",              label: "Near Miss" },
  { key: "lane_departure",         label: "Lane Departure" },
  { key: "traffic_violation",      label: "Traffic Violation" },
  { key: "tailgating",             label: "Tailgating" },
  { key: "aggressive_lane_change", label: "Aggressive Lane Change" },
  { key: "harsh_cornering",        label: "Harsh Cornering" },
  { key: "other",                  label: "Other" },
];

// ── Types ─────────────────────────────────────────────────────────────────────
interface LabelHistoryEntry {
  clip: LabelQueueItem;
  isAnomaly: boolean;
  types: string[];
  reason: string;
  labeledAt: Date;
}

// ── Synced video player ───────────────────────────────────────────────────────
function VideoPlayerPair({ frontUrl, rearUrl }: { frontUrl: string | null; rearUrl: string | null }) {
  const frontRef = useRef<HTMLVideoElement>(null);
  const rearRef  = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const syncPlay = () => {
    const f = frontRef.current; const r = rearRef.current;
    if (!f) return;
    if (playing) { f.pause(); r?.pause(); } else { f.play(); r?.play(); }
    setPlaying(p => !p);
  };
  const syncSeek = (t: number) => {
    if (frontRef.current) frontRef.current.currentTime = t;
    if (rearRef.current)  rearRef.current.currentTime  = t;
    setCurrentTime(t);
  };
  const syncReset = useCallback(() => {
    syncSeek(0); frontRef.current?.pause(); rearRef.current?.pause(); setPlaying(false);
  }, []);

  useEffect(() => { syncReset(); }, [frontUrl, rearUrl, syncReset]);

  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Front Camera", ref: frontRef, url: frontUrl, primary: true },
          { label: "Rear Camera",  ref: rearRef,  url: rearUrl,  primary: false },
        ].map(({ label, ref, url, primary }) => (
          <div key={label}>
            <p className="section-label mb-1.5">{label}</p>
            <div className="relative aspect-video flex items-center justify-center overflow-hidden rounded-xl"
                 style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              {url ? (
                <video ref={ref} src={url} className="w-full h-full object-cover"
                  onTimeUpdate={() => { if (primary) setCurrentTime(frontRef.current?.currentTime ?? 0); }}
                  onLoadedMetadata={() => { if (primary) setDuration(frontRef.current?.duration ?? 0); }}
                  onEnded={() => setPlaying(false)}
                  muted preload="metadata" />
              ) : (
                <p className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>NO VIDEO</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="panel p-3.5 space-y-2.5">
        <div className="relative w-full h-1.5 rounded-full cursor-pointer overflow-hidden"
             style={{ background: "var(--color-border)" }}
             onClick={e => {
               const rect = e.currentTarget.getBoundingClientRect();
               syncSeek(((e.clientX - rect.left) / rect.width) * duration);
             }}>
          <div className="absolute inset-y-0 left-0 rounded-full"
               style={{ width: `${pct}%`, background: "var(--color-accent)", boxShadow: "0 0 6px rgba(34,211,238,0.5)", transition: "width 0.1s" }} />
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={syncPlay} className="w-8 h-8 flex items-center justify-center rounded-lg"
                    style={{ background: "var(--color-accent)", color: "#07101E", boxShadow: "0 0 12px rgba(34,211,238,0.3)" }}>
              {playing ? <Pause size={13} strokeWidth={2.5} /> : <Play size={13} strokeWidth={2.5} />}
            </button>
            <button onClick={syncReset} className="w-8 h-8 flex items-center justify-center rounded-lg panel-sm">
              <RotateCcw size={12} style={{ color: "var(--color-ink-secondary)" }} />
            </button>
          </div>
          <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>
            {currentTime.toFixed(1)}s / {formatDuration(duration)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Anomaly label form ────────────────────────────────────────────────────────
function AnomalyLabelForm({
  onSubmit, onCancel, initialTypes = [], initialReason = "", isEdit = false,
}: {
  onSubmit: (types: string[], reason: string) => void;
  onCancel: () => void;
  initialTypes?: string[];
  initialReason?: string;
  isEdit?: boolean;
}) {
  const [selectedTypes, setSelectedTypes] = useState<string[]>(initialTypes);
  const [reason, setReason] = useState(initialReason);
  const toggle = (key: string) =>
    setSelectedTypes(prev => prev.includes(key) ? prev.filter(t => t !== key) : [...prev, key]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
      className="panel p-5 space-y-4"
      style={{ border: "1px solid rgba(244,63,94,0.2)" }}
    >
      <div className="flex items-center justify-between">
        <p className="section-label" style={{ color: "#F43F5E" }}>
          {isEdit ? "Edit Anomaly Label" : "Classify Anomaly"}
        </p>
        {isEdit && (
          <span className="font-mono text-[9px] px-2 py-0.5 rounded"
                style={{ background: "rgba(34,211,238,0.1)", border: "1px solid rgba(34,211,238,0.2)", color: "var(--color-accent)" }}>
            EDITING
          </span>
        )}
      </div>

      {/* Type toggles */}
      <div>
        <p className="font-mono text-[9px] uppercase tracking-widest mb-2.5" style={{ color: "var(--color-ink-tertiary)" }}>
          Anomaly Type <span style={{ color: "#F43F5E" }}>*</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {ANOMALY_TYPES.map(({ key, label }) => (
            <button
              key={key} onClick={() => toggle(key)}
              className="font-mono text-[10px] uppercase px-2.5 py-1.5 rounded-lg border transition-all duration-150"
              style={{
                borderColor: selectedTypes.includes(key) ? "#F43F5E" : "var(--color-border)",
                background:  selectedTypes.includes(key) ? "rgba(244,63,94,0.12)" : "transparent",
                color:       selectedTypes.includes(key) ? "#F43F5E" : "var(--color-ink-tertiary)",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Reasoning input */}
      <div>
        <p className="font-mono text-[9px] uppercase tracking-widest mb-2" style={{ color: "var(--color-ink-tertiary)" }}>
          Reasoning <span style={{ color: "var(--color-ink-tertiary)" }}>(what did you observe?)</span>
        </p>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Describe the driving behavior — e.g. 'Vehicle braked suddenly at 0:12, nearly rear-ending the car ahead. Clear near-miss scenario with less than 1 car length gap.'"
          maxLength={1000} rows={4}
          autoFocus
          className="w-full font-mono text-[12px] px-3 py-2.5 rounded-lg resize-none outline-none transition-colors"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            color: "var(--color-ink-primary)",
            lineHeight: 1.6,
          }}
          onFocus={e => { (e.target as HTMLElement).style.borderColor = "rgba(244,63,94,0.4)"; }}
          onBlur={e  => { (e.target as HTMLElement).style.borderColor = "var(--color-border)"; }}
        />
        <div className="flex justify-end mt-1">
          <span className="font-mono text-[9px]" style={{ color: reason.length > 900 ? "#F43F5E" : "var(--color-ink-tertiary)" }}>
            {reason.length} / 1000
          </span>
        </div>
      </div>

      <div className="flex gap-3">
        <button onClick={() => onSubmit(selectedTypes, reason)} className="btn-danger flex-1 justify-center">
          {isEdit ? "Update Label" : "Confirm Anomaly"}
        </button>
        <button onClick={onCancel} className="btn-secondary px-5">Cancel</button>
      </div>
    </motion.div>
  );
}

// ── Undo toast ────────────────────────────────────────────────────────────────
function UndoToast({ entry, onUndo, onDismiss }: {
  entry: LabelHistoryEntry; onUndo: () => void; onDismiss: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 5000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.96 }}
      className="fixed bottom-6 left-1/2 z-50 flex items-center gap-3 px-4 py-3 rounded-xl"
      style={{
        transform: "translateX(-50%)",
        background: "rgba(17,31,52,0.95)",
        border: "1px solid var(--color-border)",
        backdropFilter: "blur(12px)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
        minWidth: "320px",
      }}
    >
      {entry.isAnomaly
        ? <XCircle size={15} style={{ color: "#F43F5E", flexShrink: 0 }} />
        : <CheckCircle size={15} style={{ color: "#10B981", flexShrink: 0 }} />}
      <div className="flex-1 min-w-0">
        <div className="text-[12px] font-medium truncate" style={{ color: "var(--color-ink-primary)" }}>
          {entry.isAnomaly ? "Labeled as anomaly" : "Labeled as clean"}
        </div>
        <div className="font-mono text-[9px] truncate" style={{ color: "var(--color-ink-tertiary)" }}>
          {entry.clip.filename_prefix}
        </div>
      </div>
      <button
        onClick={onUndo}
        className="flex items-center gap-1.5 font-mono text-[10px] uppercase px-2.5 py-1 rounded-lg transition-all"
        style={{ border: "1px solid rgba(34,211,238,0.3)", color: "var(--color-accent)", background: "rgba(34,211,238,0.06)" }}
      >
        <Undo2 size={10} /> Undo
      </button>
    </motion.div>
  );
}

// ── History entry row ─────────────────────────────────────────────────────────
function HistoryRow({ entry, onRevisit }: { entry: LabelHistoryEntry; onRevisit: () => void }) {
  return (
    <button
      onClick={onRevisit}
      className="w-full text-left px-3 py-2.5 rounded-lg transition-all group"
      style={{ background: "transparent" }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)"; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 flex-shrink-0">
          {entry.isAnomaly
            ? <XCircle size={12} style={{ color: "#F43F5E" }} />
            : <CheckCircle size={12} style={{ color: "#10B981" }} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-mono text-[10px] truncate" style={{ color: "var(--color-ink-secondary)" }}>
            {entry.clip.filename_prefix}
          </div>
          {entry.isAnomaly && entry.types.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {entry.types.slice(0, 2).map(t => (
                <span key={t} className="font-mono text-[8px] uppercase px-1 py-0.5 rounded"
                      style={{ background: "rgba(244,63,94,0.1)", color: "#F43F5E", border: "1px solid rgba(244,63,94,0.2)" }}>
                  {anomalyLabel(t)}
                </span>
              ))}
              {entry.types.length > 2 && (
                <span className="font-mono text-[8px]" style={{ color: "var(--color-ink-tertiary)" }}>+{entry.types.length - 2}</span>
              )}
            </div>
          )}
          {entry.reason && (
            <div className="font-mono text-[9px] mt-1 line-clamp-1" style={{ color: "var(--color-ink-tertiary)", fontStyle: "italic" }}>
              "{entry.reason}"
            </div>
          )}
        </div>
        <Edit3 size={10} className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-0.5"
               style={{ color: "var(--color-accent)" }} />
      </div>
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function LabelPage() {
  const [queue, setQueue]               = useState<LabelQueueItem[]>([]);
  const [totalUnlabeled, setTotalUnlabeled] = useState(0);
  const [queueIndex, setQueueIndex]     = useState(0);
  const [page, setPage]                 = useState(1);
  const [loading, setLoading]           = useState(true);
  const [submitting, setSubmitting]     = useState(false);
  const [showAnomalyForm, setShowAnomalyForm] = useState(false);
  const [labeled, setLabeled]           = useState(0);
  const [history, setHistory]           = useState<LabelHistoryEntry[]>([]);
  const [undoEntry, setUndoEntry]       = useState<LabelHistoryEntry | null>(null);
  // For editing a history entry
  const [editingEntry, setEditingEntry] = useState<LabelHistoryEntry | null>(null);

  const fetchQueue = useCallback(() => {
    setLoading(true);
    api.labels.queue({ page, page_size: 10 })
      .then(d => { setQueue(d.clips); setTotalUnlabeled(d.total_unlabeled); setQueueIndex(0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const current = queue[queueIndex] ?? null;

  const advance = useCallback(() => {
    setShowAnomalyForm(false);
    setEditingEntry(null);
    if (queueIndex < queue.length - 1) setQueueIndex(i => i + 1);
    else setPage(p => p + 1);
  }, [queueIndex, queue.length]);

  // Submit new label
  const submitLabel = async (isAnomaly: boolean, types: string[], reason: string) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await api.labels.submit(current.id, {
        is_anomaly: isAnomaly,
        anomaly_types: types.length > 0 ? types : undefined,
        reason: reason.trim() || undefined,
      });
      const entry: LabelHistoryEntry = { clip: current, isAnomaly, types, reason, labeledAt: new Date() };
      setHistory(h => [entry, ...h.slice(0, 19)]);
      setUndoEntry(entry);
      setLabeled(l => l + 1);
      advance();
    } finally { setSubmitting(false); }
  };

  // Undo last label
  const handleUndo = async () => {
    if (!undoEntry) return;
    try {
      await api.labels.delete(undoEntry.clip.id);
      setHistory(h => h.filter(e => e.clip.id !== undoEntry.clip.id));
      setLabeled(l => Math.max(0, l - 1));
      setUndoEntry(null);
      fetchQueue();
    } catch {}
  };

  // Revisit (edit) a history entry
  const handleRevisit = (entry: LabelHistoryEntry) => {
    setEditingEntry(entry);
    setShowAnomalyForm(false);
  };

  // Submit edit for a history entry
  const submitEdit = async (isAnomaly: boolean, types: string[], reason: string) => {
    if (!editingEntry || submitting) return;
    setSubmitting(true);
    try {
      await api.labels.update(editingEntry.clip.id, {
        is_anomaly: isAnomaly,
        anomaly_types: types.length > 0 ? types : undefined,
        reason: reason.trim() || undefined,
      });
      const updated: LabelHistoryEntry = { ...editingEntry, isAnomaly, types, reason };
      setHistory(h => h.map(e => e.clip.id === editingEntry.clip.id ? updated : e));
      setEditingEntry(null);
    } finally { setSubmitting(false); }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (editingEntry) return; // disable shortcuts while editing history
      if (e.key === "u" || e.key === "U") submitLabel(false, [], "");
      if (e.key === "d" || e.key === "D") setShowAnomalyForm(true);
      if (e.key === "k" || e.key === "K") advance();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, submitting, editingEntry]);

  const progressPct = totalUnlabeled > 0 ? Math.round(((1200 - totalUnlabeled) / 1200) * 100) : 0;

  if (loading) return <LabelSkeleton />;

  return (
    <div className="p-8 max-w-[1300px]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-5">
        <p className="section-label mb-2">Ground Truth Generation</p>
        <div className="flex items-end justify-between">
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>Label Queue</h1>
          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="section-label mb-1">Session</p>
              <p className="text-display" style={{ fontSize: "1.75rem", lineHeight: 1, color: "var(--color-accent)" }}>{labeled}</p>
            </div>
            <div className="text-right">
              <p className="section-label mb-1">Remaining</p>
              <p className="text-display" style={{ fontSize: "1.75rem", lineHeight: 1 }}>{totalUnlabeled}</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Progress */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <p className="section-label">Progress</p>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>{1200 - totalUnlabeled} / 1200 labeled</span>
        </div>
        <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: "var(--color-border)" }}>
          <motion.div className="h-full rounded-full" initial={{ width: 0 }} animate={{ width: `${progressPct}%` }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
            style={{ background: "linear-gradient(90deg, #22D3EE 0%, #3B82F6 100%)", boxShadow: "0 0 10px rgba(34,211,238,0.4)" }} />
        </div>
        <div className="font-mono text-[9px] mt-1 text-right" style={{ color: "var(--color-ink-tertiary)" }}>{progressPct}% complete</div>
      </div>

      {/* Keyboard hints */}
      <div className="panel p-3 mb-5 flex items-center gap-5 flex-wrap">
        <p className="section-label">Shortcuts</p>
        {[{ key: "U", label: "Good clip" }, { key: "D", label: "Anomaly" }, { key: "K", label: "Skip" }].map(({ key, label }) => (
          <div key={key} className="flex items-center gap-1.5">
            <kbd className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                 style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-accent)" }}>{key}</kbd>
            <span className="font-mono text-[9px] uppercase tracking-wider" style={{ color: "var(--color-ink-tertiary)" }}>{label}</span>
          </div>
        ))}
        <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>
          · Click any recent label to revisit &amp; edit
        </span>
      </div>

      {/* Edit history modal overlay */}
      <AnimatePresence>
        {editingEntry && (
          <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-6"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="absolute inset-0" style={{ background: "rgba(7,16,30,0.85)", backdropFilter: "blur(8px)" }}
              onClick={() => setEditingEntry(null)} />
            <motion.div className="relative panel w-full max-w-lg z-10"
              initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}
              transition={{ type: "spring", damping: 28, stiffness: 320 }}>
              <div className="p-5">
                <div className="mb-4 pb-4" style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <p className="section-label mb-1">Revisiting Label</p>
                  <p className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>{editingEntry.clip.filename_prefix}</p>
                </div>
                {/* Toggle between clean/anomaly */}
                <div className="flex gap-3 mb-4">
                  <button
                    onClick={() => submitEdit(false, [], "")}
                    disabled={submitting}
                    className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border transition-all"
                    style={{ borderColor: "rgba(16,185,129,0.25)", background: "rgba(16,185,129,0.06)", color: "#10B981" }}
                  >
                    <ThumbsUp size={16} /> Change to Clean
                  </button>
                </div>
                <AnomalyLabelForm
                  onSubmit={(types, reason) => submitEdit(true, types, reason)}
                  onCancel={() => setEditingEntry(null)}
                  initialTypes={editingEntry.isAnomaly ? editingEntry.types : []}
                  initialReason={editingEntry.reason}
                  isEdit
                />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
               style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.2)" }}>
            <Tag size={22} style={{ color: "#10B981" }} />
          </div>
          <p className="section-label mb-2" style={{ color: "#10B981" }}>All caught up!</p>
          <p className="text-[13px]" style={{ color: "var(--color-ink-secondary)" }}>No more clips to label.</p>
        </div>
      ) : (
        <div className="grid grid-cols-12 gap-5">
          {/* Left — video + actions */}
          <AnimatePresence mode="wait">
            <motion.div key={current?.id ?? "empty"} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }} className="col-span-12 lg:col-span-8 space-y-4">
              {current && (
                <>
                  {/* Clip info */}
                  <div className="panel p-4 flex items-center justify-between">
                    <div>
                      <div className="text-[13px] font-semibold" style={{ color: "var(--color-ink-primary)", letterSpacing: "-0.01em" }}>
                        {current.filename_prefix}
                      </div>
                      <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>
                        {formatDate(current.recorded_at)} · {formatDuration(current.duration_seconds)}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>
                        {queueIndex + 1} / {queue.length} in batch
                      </span>
                    </div>
                  </div>

                  <VideoPlayerPair frontUrl={current.front_url} rearUrl={current.rear_url} />

                  {/* Action area */}
                  <AnimatePresence mode="wait">
                    {!showAnomalyForm ? (
                      <motion.div key="buttons" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }} className="grid grid-cols-3 gap-3">
                        {/* Clean */}
                        <button onClick={() => submitLabel(false, [], "")} disabled={submitting}
                          className="flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                          style={{ borderColor: "rgba(16,185,129,0.25)", background: "rgba(16,185,129,0.06)" }}
                          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.background = "rgba(16,185,129,0.12)"; el.style.borderColor = "#10B981"; }}
                          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.background = "rgba(16,185,129,0.06)"; el.style.borderColor = "rgba(16,185,129,0.25)"; }}>
                          <ThumbsUp size={22} style={{ color: "#10B981" }} />
                          <div className="text-center">
                            <div className="font-semibold text-[13px]" style={{ color: "#10B981" }}>Good Driving</div>
                            <div className="font-mono text-[9px] mt-0.5 uppercase" style={{ color: "var(--color-ink-tertiary)" }}>No anomaly</div>
                          </div>
                        </button>
                        {/* Anomaly */}
                        <button onClick={() => setShowAnomalyForm(true)} disabled={submitting}
                          className="flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                          style={{ borderColor: "rgba(244,63,94,0.25)", background: "rgba(244,63,94,0.06)" }}
                          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.background = "rgba(244,63,94,0.12)"; el.style.borderColor = "#F43F5E"; }}
                          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.background = "rgba(244,63,94,0.06)"; el.style.borderColor = "rgba(244,63,94,0.25)"; }}>
                          <ThumbsDown size={22} style={{ color: "#F43F5E" }} />
                          <div className="text-center">
                            <div className="font-semibold text-[13px]" style={{ color: "#F43F5E" }}>Anomaly</div>
                            <div className="font-mono text-[9px] mt-0.5 uppercase" style={{ color: "var(--color-ink-tertiary)" }}>Flag + classify</div>
                          </div>
                        </button>
                        {/* Skip */}
                        <button onClick={advance} disabled={submitting}
                          className="flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                          style={{ borderColor: "var(--color-border)", background: "transparent" }}
                          onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.background = "rgba(255,255,255,0.03)"; el.style.borderColor = "var(--color-muted)"; }}
                          onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.background = "transparent"; el.style.borderColor = "var(--color-border)"; }}>
                          <SkipForward size={22} style={{ color: "var(--color-ink-tertiary)" }} />
                          <div className="text-center">
                            <div className="font-semibold text-[13px]" style={{ color: "var(--color-ink-secondary)" }}>Skip</div>
                            <div className="font-mono text-[9px] mt-0.5 uppercase" style={{ color: "var(--color-ink-tertiary)" }}>Come back later</div>
                          </div>
                        </button>
                      </motion.div>
                    ) : (
                      <motion.div key="form" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                        <AnomalyLabelForm
                          onSubmit={(types, reason) => submitLabel(true, types, reason)}
                          onCancel={() => setShowAnomalyForm(false)}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Right — queue + history */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            {/* Batch queue */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="section-label">Batch Queue</p>
                <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>{totalUnlabeled} remaining</span>
              </div>
              <div className="panel overflow-hidden">
                {queue.map((item, i) => (
                  <div key={item.id}>
                    <button onClick={() => { setQueueIndex(i); setShowAnomalyForm(false); }}
                      className="w-full text-left px-4 py-3 transition-all"
                      style={{
                        borderLeft: `3px solid ${i === queueIndex ? "var(--color-accent)" : "transparent"}`,
                        background: i === queueIndex ? "rgba(34,211,238,0.06)" : "transparent",
                      }}>
                      <div className="text-[11px] font-medium truncate"
                           style={{ color: i === queueIndex ? "var(--color-ink-primary)" : "var(--color-ink-secondary)" }}>
                        {item.filename_prefix}
                      </div>
                      <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>
                        {formatDuration(item.duration_seconds)}
                      </div>
                    </button>
                    {i < queue.length - 1 && <div className="mx-4" style={{ borderTop: "1px solid var(--color-border)" }} />}
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-center gap-3 mt-3">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                  <ChevronLeft size={12} />
                </button>
                <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-secondary)" }}>Batch {page}</span>
                <button onClick={() => setPage(p => p + 1)} disabled={queue.length < 10}
                  className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                  <ChevronRight size={12} />
                </button>
              </div>
            </div>

            {/* Recent labels — revisit history */}
            {history.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="section-label">Recent Labels</p>
                  <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>
                    <Clock size={9} className="inline mr-1" />click to edit
                  </span>
                </div>
                <div className="panel overflow-hidden divide-y" style={{ borderColor: "var(--color-border)" }}>
                  {history.slice(0, 8).map((entry) => (
                    <div key={`${entry.clip.id}-${entry.labeledAt.getTime()}`}
                         style={{ borderColor: "var(--color-border)" }}>
                      <HistoryRow entry={entry} onRevisit={() => handleRevisit(entry)} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Undo toast */}
      <AnimatePresence>
        {undoEntry && (
          <UndoToast
            entry={undoEntry}
            onUndo={handleUndo}
            onDismiss={() => setUndoEntry(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function LabelSkeleton() {
  return (
    <div className="p-8">
      <Skeleton className="h-8 w-48 mb-5" />
      <Skeleton className="h-10 w-full mb-4" />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-8 space-y-4">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="aspect-video w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
        <div className="col-span-4"><Skeleton className="h-72 w-full" /></div>
      </div>
    </div>
  );
}

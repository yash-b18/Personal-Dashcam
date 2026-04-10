"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThumbsUp, ThumbsDown, SkipForward, ChevronLeft, ChevronRight, Play, Pause, RotateCcw, Tag } from "lucide-react";

import { api, LabelQueueItem } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDuration, formatDate, cn } from "@/lib/utils";

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

function VideoPlayerPair({ frontUrl, rearUrl }: { frontUrl: string | null; rearUrl: string | null }) {
  const frontRef = useRef<HTMLVideoElement>(null);
  const rearRef  = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const syncPlay = () => {
    const f = frontRef.current;
    const r = rearRef.current;
    if (!f) return;
    if (playing) { f.pause(); r?.pause(); }
    else { f.play(); r?.play(); }
    setPlaying(!playing);
  };

  const syncSeek = (time: number) => {
    if (frontRef.current) frontRef.current.currentTime = time;
    if (rearRef.current)  rearRef.current.currentTime  = time;
    setCurrentTime(time);
  };

  const syncReset = () => {
    syncSeek(0);
    frontRef.current?.pause();
    rearRef.current?.pause();
    setPlaying(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { syncReset(); }, [frontUrl, rearUrl]);

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
            <div
              className="relative aspect-video flex items-center justify-center overflow-hidden rounded-lg"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
            >
              {url ? (
                <video
                  ref={ref}
                  src={url}
                  className="w-full h-full object-cover"
                  onTimeUpdate={() => { if (primary) setCurrentTime(frontRef.current?.currentTime ?? 0); }}
                  onLoadedMetadata={() => { if (primary) setDuration(frontRef.current?.duration ?? 0); }}
                  onEnded={() => setPlaying(false)}
                  muted preload="metadata"
                />
              ) : (
                <p className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>NO VIDEO</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="panel p-3.5 space-y-2.5">
        {/* Progress */}
        <div
          className="relative w-full h-1.5 rounded-full cursor-pointer overflow-hidden"
          style={{ background: "var(--color-border)" }}
          onClick={e => {
            const rect = e.currentTarget.getBoundingClientRect();
            syncSeek(((e.clientX - rect.left) / rect.width) * duration);
          }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-all"
            style={{ width: `${pct}%`, background: "var(--color-accent)", boxShadow: "0 0 6px rgba(34,211,238,0.5)" }}
          />
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={syncPlay}
              className="w-8 h-8 flex items-center justify-center rounded-lg transition-all"
              style={{ background: "var(--color-accent)", color: "#07101E", boxShadow: "0 0 12px rgba(34,211,238,0.3)" }}
            >
              {playing ? <Pause size={13} strokeWidth={2.5} /> : <Play size={13} strokeWidth={2.5} />}
            </button>
            <button onClick={syncReset} className="w-8 h-8 flex items-center justify-center rounded-lg transition-all panel-sm">
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

function LabelForm({ onSubmit, onCancel }: { onSubmit: (types: string[], reason: string) => void; onCancel: () => void }) {
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const toggle = (key: string) => setSelectedTypes(prev => prev.includes(key) ? prev.filter(t => t !== key) : [...prev, key]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
      className="panel p-5 space-y-4"
      style={{ borderColor: "rgba(244,63,94,0.2)" }}
    >
      <div>
        <p className="section-label mb-3">Select Anomaly Types</p>
        <div className="flex flex-wrap gap-2">
          {ANOMALY_TYPES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => toggle(key)}
              className="font-mono text-[10px] uppercase px-3 py-1.5 rounded-lg border transition-all"
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
      <div>
        <p className="section-label mb-2">Reason (optional)</p>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Describe what you observed..."
          maxLength={1000} rows={3}
          className="w-full font-mono text-[12px] px-3 py-2 rounded-lg resize-none outline-none transition-colors"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            color: "var(--color-ink-primary)",
          }}
        />
      </div>
      <div className="flex gap-3">
        <button onClick={() => onSubmit(selectedTypes, reason)} className="btn-danger flex-1 justify-center">
          Confirm Anomaly
        </button>
        <button onClick={onCancel} className="btn-secondary px-5">Cancel</button>
      </div>
    </motion.div>
  );
}

export default function LabelPage() {
  const [queue, setQueue] = useState<LabelQueueItem[]>([]);
  const [totalUnlabeled, setTotalUnlabeled] = useState(0);
  const [queueIndex, setQueueIndex] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showAnomalyForm, setShowAnomalyForm] = useState(false);
  const [labeled, setLabeled] = useState(0);

  const fetchQueue = useCallback(() => {
    setLoading(true);
    api.labels.queue({ page, page_size: 10 })
      .then(d => { setQueue(d.clips); setTotalUnlabeled(d.total_unlabeled); setQueueIndex(0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const advance = useCallback(() => {
    setShowAnomalyForm(false);
    if (queueIndex < queue.length - 1) setQueueIndex(i => i + 1);
    else setPage(p => p + 1);
  }, [queueIndex, queue.length]);

  const handleGood = async () => {
    if (!current || submitting) return;
    setSubmitting(true);
    try { await api.labels.submit(current.id, { is_anomaly: false }); setLabeled(l => l + 1); advance(); }
    finally { setSubmitting(false); }
  };

  const handleAnomalySubmit = async (types: string[], reason: string) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await api.labels.submit(current.id, { is_anomaly: true, anomaly_types: types.length > 0 ? types : undefined, reason: reason.trim() || undefined });
      setLabeled(l => l + 1); advance();
    } finally { setSubmitting(false); }
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "u" || e.key === "U") handleGood();
      if (e.key === "d" || e.key === "D") setShowAnomalyForm(true);
      if (e.key === "k" || e.key === "K") advance();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, queueIndex]);

  const current = queue[queueIndex] ?? null;
  const progressPct = totalUnlabeled > 0 ? Math.round(((1200 - totalUnlabeled) / 1200) * 100) : 0;

  if (loading) return <LabelSkeleton />;

  return (
    <div className="p-8 max-w-[1200px]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <p className="section-label mb-2">Ground Truth Generation</p>
        <div className="flex items-end justify-between">
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>Label Queue</h1>
          <div className="text-right">
            <p className="section-label mb-1.5">Session Labeled</p>
            <p className="text-display" style={{ fontSize: "2rem", lineHeight: 1, color: "var(--color-accent)" }}>{labeled}</p>
          </div>
        </div>
      </motion.div>

      {/* Progress */}
      <div className="panel p-4 mb-5">
        <div className="flex items-center justify-between mb-2.5">
          <p className="section-label">Labeling Progress</p>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>{1200 - totalUnlabeled} / 1200</span>
        </div>
        <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: "var(--color-border)" }}>
          <motion.div
            className="h-full rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
            style={{ background: "linear-gradient(90deg, #22D3EE 0%, #3B82F6 100%)", boxShadow: "0 0 10px rgba(34,211,238,0.4)" }}
          />
        </div>
        <div className="font-mono text-[9px] mt-1.5 text-right" style={{ color: "var(--color-ink-tertiary)" }}>{progressPct}% complete</div>
      </div>

      {/* Keyboard hints */}
      <div className="panel p-3 mb-5 flex items-center gap-6 flex-wrap">
        <p className="section-label">Shortcuts</p>
        {[{ key: "U", label: "Good clip" }, { key: "D", label: "Anomaly" }, { key: "K", label: "Skip" }, { key: "SPACE", label: "Play/Pause" }].map(({ key, label }) => (
          <div key={key} className="flex items-center gap-1.5">
            <kbd className="font-mono text-[9px] px-1.5 py-0.5 rounded" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-accent)" }}>{key}</kbd>
            <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
          </div>
        ))}
      </div>

      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4" style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.2)" }}>
            <Tag size={22} style={{ color: "#10B981" }} />
          </div>
          <p className="section-label mb-2" style={{ color: "#10B981" }}>All caught up!</p>
          <p className="text-[13px]" style={{ color: "var(--color-ink-secondary)" }}>No more clips to label. Great work.</p>
        </div>
      ) : current ? (
        <div className="grid grid-cols-12 gap-5">
          {/* Video + actions */}
          <motion.div key={current.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }} className="col-span-12 lg:col-span-8 space-y-4">
            <div className="panel p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-[12px] font-medium" style={{ color: "var(--color-ink-primary)" }}>{current.filename_prefix}</div>
                  <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>
                    {formatDate(current.recorded_at)} · {formatDuration(current.duration_seconds)}
                  </div>
                </div>
                <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>{queueIndex + 1} / {queue.length}</span>
              </div>
            </div>

            <VideoPlayerPair frontUrl={current.front_url} rearUrl={current.rear_url} />

            <AnimatePresence mode="wait">
              {!showAnomalyForm ? (
                <motion.div key="buttons" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="grid grid-cols-3 gap-3">
                  {/* Good */}
                  <button onClick={handleGood} disabled={submitting}
                    className="group flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                    style={{ borderColor: "rgba(16,185,129,0.25)", background: "rgba(16,185,129,0.06)" }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(16,185,129,0.12)"; (e.currentTarget as HTMLElement).style.borderColor = "#10B981"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "rgba(16,185,129,0.06)"; (e.currentTarget as HTMLElement).style.borderColor = "rgba(16,185,129,0.25)"; }}
                  >
                    <ThumbsUp size={22} style={{ color: "#10B981" }} />
                    <div className="text-center">
                      <div className="font-semibold text-[13px]" style={{ color: "#10B981" }}>Good Driving</div>
                      <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)", textTransform: "uppercase" }}>No anomaly</div>
                    </div>
                  </button>
                  {/* Anomaly */}
                  <button onClick={() => setShowAnomalyForm(true)} disabled={submitting}
                    className="group flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                    style={{ borderColor: "rgba(244,63,94,0.25)", background: "rgba(244,63,94,0.06)" }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(244,63,94,0.12)"; (e.currentTarget as HTMLElement).style.borderColor = "#F43F5E"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "rgba(244,63,94,0.06)"; (e.currentTarget as HTMLElement).style.borderColor = "rgba(244,63,94,0.25)"; }}
                  >
                    <ThumbsDown size={22} style={{ color: "#F43F5E" }} />
                    <div className="text-center">
                      <div className="font-semibold text-[13px]" style={{ color: "#F43F5E" }}>Anomaly</div>
                      <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)", textTransform: "uppercase" }}>Flag + classify</div>
                    </div>
                  </button>
                  {/* Skip */}
                  <button onClick={advance} disabled={submitting}
                    className="group flex flex-col items-center gap-2.5 py-5 rounded-xl border transition-all duration-200 disabled:opacity-50"
                    style={{ borderColor: "var(--color-border)", background: "transparent" }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--color-muted)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.borderColor = "var(--color-border)"; }}
                  >
                    <SkipForward size={22} style={{ color: "var(--color-ink-tertiary)" }} />
                    <div className="text-center">
                      <div className="font-semibold text-[13px]" style={{ color: "var(--color-ink-secondary)" }}>Skip</div>
                      <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)", textTransform: "uppercase" }}>Come back later</div>
                    </div>
                  </button>
                </motion.div>
              ) : (
                <motion.div key="form" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                  <LabelForm onSubmit={handleAnomalySubmit} onCancel={() => setShowAnomalyForm(false)} />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* Queue list */}
          <div className="col-span-12 lg:col-span-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="section-label">Batch Queue</p>
              <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>{totalUnlabeled} left</span>
            </div>
            <div className="panel overflow-hidden">
              {queue.map((item, i) => (
                <div key={item.id}>
                  <button
                    onClick={() => { setQueueIndex(i); setShowAnomalyForm(false); }}
                    className="w-full text-left px-4 py-3 transition-all"
                    style={{
                      borderLeft: `3px solid ${i === queueIndex ? "var(--color-accent)" : "transparent"}`,
                      background: i === queueIndex ? "rgba(34,211,238,0.06)" : "transparent",
                    }}
                  >
                    <div className="text-[11px] font-medium truncate" style={{ color: i === queueIndex ? "var(--color-ink-primary)" : "var(--color-ink-secondary)" }}>
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
            <div className="flex items-center justify-center gap-3">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                <ChevronLeft size={12} />
              </button>
              <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-secondary)" }}>Batch {page}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={queue.length < 10} className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                <ChevronRight size={12} />
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LabelSkeleton() {
  return (
    <div className="p-8">
      <Skeleton className="h-8 w-48 mb-5" />
      <Skeleton className="h-12 w-full mb-4" />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-8 space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="aspect-video w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
        <div className="col-span-4"><Skeleton className="h-64 w-full" /></div>
      </div>
    </div>
  );
}

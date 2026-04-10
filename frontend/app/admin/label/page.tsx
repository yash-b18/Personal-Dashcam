"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ThumbsUp, ThumbsDown, SkipForward, ChevronLeft, ChevronRight,
  Play, Pause, RotateCcw, Tag,
} from "lucide-react";

import { api, LabelQueueItem } from "@/lib/api";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
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

// ── Synced video player pair ──────────────────────────────────────────────────
function VideoPlayerPair({
  frontUrl,
  rearUrl,
}: {
  frontUrl: string | null;
  rearUrl: string | null;
}) {
  const frontRef = useRef<HTMLVideoElement>(null);
  const rearRef  = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const syncPlay = () => {
    const f = frontRef.current;
    const r = rearRef.current;
    if (!f) return;
    if (playing) {
      f.pause(); r?.pause();
    } else {
      f.play(); r?.play();
    }
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

  useEffect(() => {
    syncReset();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frontUrl, rearUrl]);

  const handleTimeUpdate = () => {
    setCurrentTime(frontRef.current?.currentTime ?? 0);
  };

  const handleLoadedMetadata = () => {
    setDuration(frontRef.current?.duration ?? 0);
  };

  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="space-y-3">
      {/* Video grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Front cam */}
        <div className="space-y-1">
          <p className="section-label">FRONT CAMERA</p>
          <div className="relative aspect-video bg-surface border border-border rounded-sm overflow-hidden">
            {frontUrl ? (
              <video
                ref={frontRef}
                src={frontUrl}
                className="w-full h-full object-cover"
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
                onEnded={() => setPlaying(false)}
                muted
                preload="metadata"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-label text-ink-tertiary">NO FRONT VIDEO</p>
              </div>
            )}
          </div>
        </div>

        {/* Rear cam */}
        <div className="space-y-1">
          <p className="section-label">REAR CAMERA</p>
          <div className="relative aspect-video bg-surface border border-border rounded-sm overflow-hidden">
            {rearUrl ? (
              <video
                ref={rearRef}
                src={rearUrl}
                className="w-full h-full object-cover"
                muted
                preload="metadata"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-label text-ink-tertiary">NO REAR VIDEO</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Playback controls */}
      <div className="panel p-3 space-y-2">
        {/* Progress bar */}
        <div
          className="relative w-full h-1.5 bg-border rounded-full cursor-pointer"
          onClick={e => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            syncSeek(pct * duration);
          }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-amber-DEFAULT transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={syncPlay}
              className="w-8 h-8 flex items-center justify-center bg-amber-DEFAULT rounded-sm text-void hover:bg-amber-glow transition-colors"
            >
              {playing ? <Pause size={14} strokeWidth={2.5} /> : <Play size={14} strokeWidth={2.5} />}
            </button>
            <button
              onClick={syncReset}
              className="w-8 h-8 flex items-center justify-center panel rounded-sm text-ink-secondary hover:text-ink-primary transition-colors"
            >
              <RotateCcw size={12} />
            </button>
          </div>
          <span className="font-mono text-[10px] text-ink-tertiary">
            {currentTime.toFixed(1)}s / {formatDuration(duration)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Label form modal ──────────────────────────────────────────────────────────
function LabelForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (types: string[], reason: string) => void;
  onCancel: () => void;
}) {
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [reason, setReason] = useState("");

  const toggle = (key: string) => {
    setSelectedTypes(prev =>
      prev.includes(key) ? prev.filter(t => t !== key) : [...prev, key]
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="panel panel-accent p-5 space-y-4"
    >
      <div>
        <p className="section-label mb-3">SELECT ANOMALY TYPES</p>
        <div className="flex flex-wrap gap-2">
          {ANOMALY_TYPES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => toggle(key)}
              className={cn(
                "font-mono text-[10px] uppercase px-2.5 py-1.5 rounded-sm border transition-all",
                selectedTypes.includes(key)
                  ? "border-amber-DEFAULT bg-amber-subtle text-amber-DEFAULT"
                  : "border-border text-ink-tertiary hover:border-muted hover:text-ink-secondary"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="section-label mb-2">REASON (OPTIONAL)</p>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Describe what you observed..."
          maxLength={1000}
          rows={3}
          className="w-full bg-surface border border-border rounded-sm px-3 py-2 font-mono text-[12px] text-ink-primary placeholder:text-ink-tertiary resize-none focus:border-amber-dim outline-none"
        />
      </div>

      <div className="flex gap-3">
        <button
          onClick={() => onSubmit(selectedTypes, reason)}
          className="flex-1 py-2.5 bg-crimson border border-crimson text-white font-mono text-[11px] uppercase tracking-widest rounded-sm hover:bg-red-500 transition-colors"
        >
          CONFIRM ANOMALY
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2.5 panel font-mono text-[11px] uppercase tracking-widest text-ink-secondary hover:text-ink-primary transition-colors rounded-sm"
        >
          CANCEL
        </button>
      </div>
    </motion.div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
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
      .then(d => {
        setQueue(d.clips);
        setTotalUnlabeled(d.total_unlabeled);
        setQueueIndex(0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case "u": case "U": handleGood(); break;
        case "d": case "D": setShowAnomalyForm(true); break;
        case "k": case "K": handleSkip(); break;
        case " ": e.preventDefault(); break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, queueIndex]);

  const current = queue[queueIndex] ?? null;

  const advance = useCallback(() => {
    setShowAnomalyForm(false);
    if (queueIndex < queue.length - 1) {
      setQueueIndex(i => i + 1);
    } else {
      setPage(p => p + 1);
    }
  }, [queueIndex, queue.length]);

  const handleGood = async () => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await api.labels.submit(current.id, { is_anomaly: false });
      setLabeled(l => l + 1);
      advance();
    } finally {
      setSubmitting(false);
    }
  };

  const handleAnomalySubmit = async (types: string[], reason: string) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await api.labels.submit(current.id, {
        is_anomaly: true,
        anomaly_types: types.length > 0 ? types : undefined,
        reason: reason.trim() || undefined,
      });
      setLabeled(l => l + 1);
      advance();
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = () => {
    if (!current) return;
    advance();
  };

  const total = totalUnlabeled;
  const progressPct = total > 0 ? Math.round(((1200 - total) / 1200) * 100) : 0;

  if (loading) return <LabelSkeleton />;

  return (
    <div className="p-8 max-w-[1200px]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6">
        <p className="section-label mb-1">GROUND TRUTH GENERATION</p>
        <div className="flex items-end justify-between">
          <h1 className="font-display text-4xl font-extrabold tracking-wide"
              style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 900, fontSize: "2.5rem", letterSpacing: "0.04em" }}>
            LABEL QUEUE
          </h1>
          <div className="text-right">
            <p className="section-label mb-1">SESSION LABELED</p>
            <p className="font-display text-3xl font-extrabold text-amber-DEFAULT"
               style={{ fontFamily: "'Barlow Condensed'", fontWeight: 800 }}>
              {labeled}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Progress bar */}
      <div className="panel p-4 mb-6">
        <div className="flex items-center justify-between mb-2">
          <p className="section-label">OVERALL LABELING PROGRESS</p>
          <span className="font-mono text-[11px] text-ink-secondary">
            {1200 - total} / 1200 clips labeled
          </span>
        </div>
        <div className="w-full h-2 bg-border rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-amber-DEFAULT rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
            style={{ boxShadow: "0 0 8px rgba(245,158,11,0.5)" }}
          />
        </div>
        <div className="mt-1.5 font-mono text-[9px] text-ink-tertiary text-right">{progressPct}% complete</div>
      </div>

      {/* Keyboard shortcuts hint */}
      <div className="panel p-3 mb-6 flex items-center gap-6">
        <p className="section-label">SHORTCUTS</p>
        {[
          { key: "U", label: "GOOD (no anomaly)" },
          { key: "D", label: "ANOMALY detected" },
          { key: "K", label: "SKIP" },
          { key: "SPACE", label: "PLAY/PAUSE" },
        ].map(({ key, label }) => (
          <div key={key} className="flex items-center gap-1.5">
            <kbd className="font-mono text-[9px] px-1.5 py-0.5 bg-surface border border-border rounded-sm text-amber-DEFAULT">{key}</kbd>
            <span className="text-label text-ink-tertiary">{label}</span>
          </div>
        ))}
      </div>

      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24">
          <Tag size={40} className="text-emerald-400 mb-4" />
          <p className="section-label mb-2 text-emerald-400">ALL CAUGHT UP</p>
          <p className="text-data text-ink-secondary">No more clips in the queue. Great work!</p>
        </div>
      ) : current ? (
        <div className="grid grid-cols-12 gap-5">
          {/* Video player — main */}
          <motion.div
            key={current.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="col-span-12 lg:col-span-8 space-y-5"
          >
            {/* Clip info */}
            <div className="panel p-4">
              <div className="flex items-start justify-between mb-1">
                <p className="font-mono text-[11px] text-ink-primary">{current.filename_prefix}</p>
                <span className="font-mono text-[10px] text-ink-tertiary">
                  {queueIndex + 1} of {queue.length} in batch
                </span>
              </div>
              <p className="font-mono text-[9px] text-ink-tertiary">
                {formatDate(current.recorded_at)} · {formatDuration(current.duration_seconds)}
              </p>
            </div>

            <VideoPlayerPair frontUrl={current.front_url} rearUrl={current.rear_url} />

            {/* Action buttons */}
            <AnimatePresence mode="wait">
              {!showAnomalyForm ? (
                <motion.div
                  key="buttons"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="grid grid-cols-3 gap-3"
                >
                  {/* Good driving */}
                  <button
                    onClick={handleGood}
                    disabled={submitting}
                    className={cn(
                      "group flex flex-col items-center gap-2 py-5 rounded-sm border transition-all duration-200",
                      "border-emerald-400/30 bg-emerald-400/5 hover:bg-emerald-400/15 hover:border-emerald-400",
                      "text-emerald-400 disabled:opacity-50"
                    )}
                  >
                    <ThumbsUp size={24} className="group-hover:scale-110 transition-transform" />
                    <div className="text-center">
                      <div className="font-display text-base font-bold leading-none"
                           style={{ fontFamily: "'Barlow Condensed'", fontWeight: 700, fontSize: "1.1rem" }}>
                        GOOD DRIVING
                      </div>
                      <div className="text-label opacity-60 mt-0.5">No anomaly</div>
                    </div>
                  </button>

                  {/* Anomaly */}
                  <button
                    onClick={() => setShowAnomalyForm(true)}
                    disabled={submitting}
                    className={cn(
                      "group flex flex-col items-center gap-2 py-5 rounded-sm border transition-all duration-200",
                      "border-crimson/30 bg-crimson/5 hover:bg-crimson/15 hover:border-crimson",
                      "text-crimson disabled:opacity-50"
                    )}
                  >
                    <ThumbsDown size={24} className="group-hover:scale-110 transition-transform" />
                    <div className="text-center">
                      <div className="font-display text-base font-bold leading-none"
                           style={{ fontFamily: "'Barlow Condensed'", fontWeight: 700, fontSize: "1.1rem" }}>
                        ANOMALY
                      </div>
                      <div className="text-label opacity-60 mt-0.5">Flag + classify</div>
                    </div>
                  </button>

                  {/* Skip */}
                  <button
                    onClick={handleSkip}
                    disabled={submitting}
                    className={cn(
                      "group flex flex-col items-center gap-2 py-5 rounded-sm border transition-all duration-200",
                      "border-border bg-surface/50 hover:border-muted hover:bg-surface",
                      "text-ink-tertiary hover:text-ink-secondary disabled:opacity-50"
                    )}
                  >
                    <SkipForward size={24} className="group-hover:scale-110 transition-transform" />
                    <div className="text-center">
                      <div className="font-display text-base font-bold leading-none"
                           style={{ fontFamily: "'Barlow Condensed'", fontWeight: 700, fontSize: "1.1rem" }}>
                        SKIP
                      </div>
                      <div className="text-label opacity-60 mt-0.5">Come back later</div>
                    </div>
                  </button>
                </motion.div>
              ) : (
                <motion.div key="form" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                  <LabelForm
                    onSubmit={handleAnomalySubmit}
                    onCancel={() => setShowAnomalyForm(false)}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* Queue sidebar */}
          <div className="col-span-12 lg:col-span-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="section-label">BATCH QUEUE</p>
              <span className="font-mono text-[10px] text-ink-tertiary">{totalUnlabeled} remaining</span>
            </div>
            <ul className="panel overflow-hidden">
              {queue.map((item, i) => (
                <li key={item.id}>
                  <button
                    onClick={() => { setQueueIndex(i); setShowAnomalyForm(false); }}
                    className={cn(
                      "w-full text-left px-4 py-3 transition-colors",
                      i === queueIndex
                        ? "bg-amber-subtle border-l-2 border-l-amber-DEFAULT"
                        : "hover:bg-surface border-l-2 border-l-transparent"
                    )}
                  >
                    <div className="font-mono text-[10px] text-ink-primary truncate">{item.filename_prefix}</div>
                    <div className="font-mono text-[8px] text-ink-tertiary mt-0.5">{formatDuration(item.duration_seconds)}</div>
                  </button>
                  {i < queue.length - 1 && <div className="mx-4 border-t border-border" />}
                </li>
              ))}
            </ul>

            {/* Batch pagination */}
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30"
              >
                <ChevronLeft size={12} />
              </button>
              <span className="font-mono text-[10px] text-ink-secondary">Batch {page}</span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={queue.length < 10}
                className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30"
              >
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
      <Skeleton className="h-8 w-48 mb-6" />
      <Skeleton className="h-12 w-full mb-5" />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-8 space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="aspect-video w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
        <div className="col-span-4">
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    </div>
  );
}

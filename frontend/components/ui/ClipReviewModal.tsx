"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Play,
  Pause,
  Volume2,
  VolumeX,
  AlertTriangle,
  ShieldCheck,
  Clock,
  Calendar,
  Film,
  RefreshCw,
} from "lucide-react";

import { api, ClipDetail, AnomalySummary } from "@/lib/api";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDate, formatDuration, scoreToColor } from "@/lib/utils";

interface ClipReviewModalProps {
  clipId: string | null;
  onClose: () => void;
  onReprocess?: (id: string) => Promise<void>;
}

function secondsToClock(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

/** Four cyan L-brackets over a rectangle — forensic targeting reticle. */
function Crosshairs() {
  const L = 20;
  const stroke = "rgba(34,211,238,0.8)";
  const glow = "drop-shadow(0 0 4px rgba(34,211,238,0.5))";
  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none"
    >
      {/* top-left */}
      <path d={`M 0,${L} L 0,0 L ${L},0`} fill="none" stroke={stroke} strokeWidth="2"
            style={{ filter: glow }} vectorEffect="non-scaling-stroke" />
      {/* top-right */}
      <path d={`M ${100 - L},0 L 100,0 L 100,${L}`} fill="none" stroke={stroke} strokeWidth="2"
            style={{ filter: glow }} vectorEffect="non-scaling-stroke" />
      {/* bottom-left */}
      <path d={`M 0,${100 - L} L 0,100 L ${L},100`} fill="none" stroke={stroke} strokeWidth="2"
            style={{ filter: glow }} vectorEffect="non-scaling-stroke" />
      {/* bottom-right */}
      <path d={`M ${100 - L},100 L 100,100 L 100,${100 - L}`} fill="none" stroke={stroke} strokeWidth="2"
            style={{ filter: glow }} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function ClipReviewModal({ clipId, onClose, onReprocess }: ClipReviewModalProps) {
  const [clip, setClip] = useState<ClipDetail | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [reprocessing, setReprocessing] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const refetch = useCallback(async () => {
    if (!clipId) return;
    try {
      const [c, a] = await Promise.all([
        api.clips.get(clipId),
        api.anomalies.list({ clip_id: clipId, page_size: 100 }).catch(() => ({ anomalies: [] as AnomalySummary[] })),
      ]);
      setClip(c);
      setAnomalies(a.anomalies);
    } catch { /* silent — keep stale data rather than wiping UI */ }
  }, [clipId]);

  // Fetch clip + anomalies whenever clipId changes
  useEffect(() => {
    if (!clipId) return;
    setClip(null);
    setAnomalies([]);
    setLoading(true);
    refetch().finally(() => setLoading(false));
  }, [clipId, refetch]);

  // Auto-poll while the clip is in the processing state so the modal updates
  // in-place from "Processing…" to the full AI Analysis when the task finishes.
  useEffect(() => {
    if (clip?.processing_status !== "processing") return;
    const id = setInterval(refetch, 5000);
    return () => clearInterval(id);
  }, [clip?.processing_status, refetch]);

  // Reset video state when modal closes
  useEffect(() => {
    if (!clipId) {
      setPlaying(false);
      setProgress(0);
      setDuration(0);
    }
  }, [clipId]);

  // Keyboard: Esc to close, Space to play/pause
  useEffect(() => {
    if (!clipId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " " && videoRef.current) {
        e.preventDefault();
        if (videoRef.current.paused) videoRef.current.play();
        else videoRef.current.pause();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clipId, onClose]);

  // Lock body scroll while open
  useEffect(() => {
    if (clipId) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = prev; };
    }
  }, [clipId]);

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };

  const onSeek = (pct: number) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    v.currentTime = duration * pct;
  };

  const handleReprocess = async () => {
    if (!clipId || !onReprocess) return;
    setReprocessing(true);
    try {
      await onReprocess(clipId);
      // Stay open — refetch so the user sees the new PROCESSING state in-place.
      await refetch();
    } finally {
      setReprocessing(false);
    }
  };

  // ── Body wheel capture ────────────────────────────────────────────────────
  // Some nested elements (video, framer-motion overlays) can swallow wheel
  // events. Attach a non-passive wheel listener on the scroll body so we can
  // always route the wheel delta into body scrollTop.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY === 0) return;
      // If a nested scroll container (e.g. the inner anomaly list) is under the
      // cursor and can still scroll in the wheel direction, let the browser
      // handle it natively — don't preventDefault or reroute.
      let node = e.target as HTMLElement | null;
      while (node && node !== el) {
        const style = window.getComputedStyle(node);
        const scrolls = /(auto|scroll)/.test(style.overflowY);
        if (scrolls && node.scrollHeight > node.clientHeight) {
          const canGoDown = node.scrollTop + node.clientHeight < node.scrollHeight - 1;
          const canGoUp = node.scrollTop > 0;
          if ((e.deltaY > 0 && canGoDown) || (e.deltaY < 0 && canGoUp)) {
            return; // Let the inner container consume the wheel.
          }
        }
        node = node.parentElement;
      }
      const atTop = el.scrollTop <= 0 && e.deltaY < 0;
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1 && e.deltaY > 0;
      if (atTop || atBottom) return;
      e.preventDefault();
      el.scrollTop += e.deltaY;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [clipId]);

  // ── Derived verdict ───────────────────────────────────────────────────────
  const hasAnomalies = anomalies.length > 0;
  const primaryExplanation = anomalies.find(a => a.ai_explanation)?.ai_explanation ?? null;

  // Group anomalies by timestamp for timeline
  const timelineMarks = anomalies
    .filter(a => a.timestamp_end > a.timestamp_start)
    .map(a => ({
      startPct: duration > 0 ? (a.timestamp_start / duration) * 100 : 0,
      endPct:   duration > 0 ? (a.timestamp_end   / duration) * 100 : 0,
      severity: a.severity,
      model:    a.model_type,
    }));

  const scoreColor = clip?.score != null ? scoreToColor(clip.score) : "var(--color-ink-tertiary)";

  return (
    <AnimatePresence>
      {clipId && (
        <motion.div
          key="backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-8"
          style={{
            background: "rgba(4, 10, 20, 0.75)",
            backdropFilter: "blur(10px)",
            WebkitBackdropFilter: "blur(10px)",
          }}
        >
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-5xl overflow-hidden flex flex-col"
            style={{
              background: "linear-gradient(180deg, #0B1726 0%, #091523 100%)",
              border: "1px solid rgba(34,211,238,0.18)",
              borderRadius: 16,
              boxShadow:
                "0 0 0 1px rgba(34,211,238,0.05), 0 24px 80px rgba(0,0,0,0.6), 0 0 120px rgba(34,211,238,0.08)",
              maxHeight: "92vh",
              height: "92vh",
            }}
          >
            {/* Atmospheric top-glow */}
            <div
              className="absolute inset-x-0 top-0 h-40 pointer-events-none opacity-70"
              style={{
                background:
                  "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(34,211,238,0.18) 0%, transparent 70%)",
              }}
            />

            {/* ── Header strip ─────────────────────────────────────────── */}
            <div
              className="relative flex items-center justify-between px-7 py-4"
              style={{ borderBottom: "1px solid rgba(34,211,238,0.1)" }}
            >
              <div className="flex items-center gap-4 min-w-0">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full animate-pulse"
                    style={{ background: "#22D3EE", boxShadow: "0 0 10px #22D3EE" }}
                  />
                  <span
                    className="font-mono text-[10px] uppercase tracking-[0.22em]"
                    style={{ color: "var(--color-accent)" }}
                  >
                    Clip Review
                  </span>
                </div>
                <div
                  className="h-4 w-px"
                  style={{ background: "rgba(34,211,238,0.18)" }}
                />
                <div className="min-w-0">
                  <div
                    className="text-[14px] font-semibold tracking-tight truncate"
                    style={{ color: "var(--color-ink-primary)" }}
                  >
                    {clip?.filename_prefix ?? "Loading…"}
                  </div>
                  <div
                    className="font-mono text-[10px] mt-0.5 flex items-center gap-3 tracking-wider uppercase"
                    style={{ color: "var(--color-ink-tertiary)" }}
                  >
                    {clip?.recorded_at && (
                      <span className="flex items-center gap-1.5">
                        <Calendar size={10} /> {formatDate(clip.recorded_at)}
                      </span>
                    )}
                    {clip?.duration_seconds != null && (
                      <span className="flex items-center gap-1.5">
                        <Clock size={10} /> {formatDuration(clip.duration_seconds)}
                      </span>
                    )}
                    {clip && <StatusBadge status={clip.processing_status} />}
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="w-9 h-9 flex items-center justify-center rounded-lg transition-all"
                style={{
                  background: "rgba(34,211,238,0.06)",
                  border: "1px solid rgba(34,211,238,0.2)",
                  color: "var(--color-accent)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(34,211,238,0.15)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "rgba(34,211,238,0.06)";
                }}
              >
                <X size={15} />
              </button>
            </div>

            {/* ── Body (scrollable) ────────────────────────────────────── */}
            <div
              ref={bodyRef}
              className="clip-review-scroll relative flex flex-col gap-6"
              style={{
                flex: "1 1 0",
                minHeight: 0,
                overflowY: "scroll",
                overflowX: "hidden",
                overscrollBehavior: "contain",
                padding: "24px 28px 40px 28px",
              }}
            >
              {/* ── Video theater + verdict ──────────────────────────── */}
              <div className="grid grid-cols-1 lg:grid-cols-[1.55fr,1fr] gap-5">
                {/* Video theater */}
                <div
                  className="relative aspect-video rounded-lg overflow-hidden"
                  style={{
                    background: "#000",
                    border: "1px solid rgba(34,211,238,0.12)",
                    maxHeight: 340,
                  }}
                >
                  {clip?.front_url ? (
                    <>
                      <video
                        ref={videoRef}
                        src={clip.front_url}
                        className="w-full h-full object-contain"
                        muted={muted}
                        onPlay={() => setPlaying(true)}
                        onPause={() => setPlaying(false)}
                        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
                        onTimeUpdate={(e) => setProgress(e.currentTarget.currentTime)}
                        onClick={togglePlay}
                      />
                      {/* Scan-line overlay + gradient */}
                      <div
                        className="absolute inset-0 pointer-events-none mix-blend-overlay opacity-20"
                        style={{
                          background:
                            "repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(34,211,238,0.08) 2px, rgba(34,211,238,0.08) 3px)",
                        }}
                      />
                      <div
                        className="absolute inset-0 pointer-events-none"
                        style={{
                          background:
                            "radial-gradient(ellipse 100% 100% at 50% 50%, transparent 60%, rgba(0,0,0,0.4) 100%)",
                        }}
                      />
                      <Crosshairs />

                      {/* Top-left REC indicator */}
                      <div
                        className="absolute top-3 left-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] pointer-events-none"
                        style={{ color: "rgba(234,242,255,0.8)" }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full"
                          style={{
                            background: playing ? "#F43F5E" : "#7A9CC0",
                            boxShadow: playing ? "0 0 8px #F43F5E" : "none",
                            animation: playing ? "pulse 1s ease-in-out infinite" : "none",
                          }}
                        />
                        {playing ? "Live" : "Paused"}
                      </div>

                      {/* Bottom controls */}
                      <div
                        className="absolute bottom-0 left-0 right-0 px-3 py-2.5 flex items-center gap-3"
                        style={{
                          background:
                            "linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.75) 60%)",
                        }}
                      >
                        <button
                          onClick={togglePlay}
                          className="w-8 h-8 flex items-center justify-center rounded-full transition-all"
                          style={{
                            background: "rgba(34,211,238,0.15)",
                            border: "1px solid rgba(34,211,238,0.4)",
                            color: "var(--color-accent)",
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.3)")}
                          onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.15)")}
                        >
                          {playing ? <Pause size={13} /> : <Play size={13} style={{ marginLeft: 1 }} />}
                        </button>

                        {/* Progress bar */}
                        <div
                          className="relative flex-1 h-1 rounded-full cursor-pointer group"
                          style={{ background: "rgba(255,255,255,0.1)" }}
                          onClick={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect();
                            onSeek((e.clientX - rect.left) / rect.width);
                          }}
                        >
                          {/* Anomaly segments */}
                          {timelineMarks.map((m, i) => (
                            <div
                              key={i}
                              className="absolute top-0 bottom-0"
                              style={{
                                left: `${m.startPct}%`,
                                width: `${Math.max(0.4, m.endPct - m.startPct)}%`,
                                background: m.severity > 0.7 ? "#F43F5E" : "#F59E0B",
                                opacity: 0.7,
                              }}
                            />
                          ))}
                          {/* Playhead fill */}
                          <div
                            className="absolute inset-y-0 left-0 rounded-full"
                            style={{
                              width: `${duration ? (progress / duration) * 100 : 0}%`,
                              background: "var(--color-accent)",
                              boxShadow: "0 0 8px rgba(34,211,238,0.6)",
                            }}
                          />
                        </div>

                        <span
                          className="font-mono text-[10px] tabular-nums"
                          style={{ color: "var(--color-ink-secondary)" }}
                        >
                          {secondsToClock(progress)} / {secondsToClock(duration)}
                        </span>

                        <button
                          onClick={toggleMute}
                          className="w-7 h-7 flex items-center justify-center rounded-md"
                          style={{ color: "var(--color-ink-secondary)" }}
                        >
                          {muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                      <Film size={26} style={{ color: "var(--color-ink-tertiary)" }} />
                      <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--color-ink-tertiary)" }}>
                        {loading ? "Loading clip…" : "No video source"}
                      </span>
                    </div>
                  )}
                </div>

                {/* Verdict column */}
                <div className="flex flex-col gap-4">
                  <VerdictCard
                    hasAnomalies={hasAnomalies}
                    loading={loading}
                    status={clip?.processing_status ?? "pending"}
                    anomalyCount={anomalies.length}
                  />

                  {/* Score readout */}
                  <div
                    className="p-4 rounded-lg"
                    style={{
                      background: "rgba(12,25,40,0.6)",
                      border: "1px solid var(--color-border)",
                    }}
                  >
                    <div className="section-label mb-2">Driver Score</div>
                    <div className="flex items-baseline gap-2">
                      <span
                        className="text-display tabular-nums"
                        style={{ fontSize: "2.4rem", lineHeight: 0.9, color: scoreColor }}
                      >
                        {clip?.score != null ? Math.round(clip.score) : "—"}
                      </span>
                      {clip?.grade && (
                        <span
                          className="font-mono text-[11px] font-semibold tracking-widest"
                          style={{ color: scoreColor }}
                        >
                          GRADE {clip.grade}
                        </span>
                      )}
                    </div>
                    <div
                      className="mt-3 pt-3 font-mono text-[10px] uppercase tracking-[0.14em] flex justify-between"
                      style={{ color: "var(--color-ink-tertiary)", borderTop: "1px dashed rgba(28,45,68,0.8)" }}
                    >
                      <span>{anomalies.length} events</span>
                      <span>{clip?.processed_at ? "Analyzed" : "Unprocessed"}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Bottom panel: AI Analysis OR Process CTA ───────────── */}
              {loading ? (
                <div
                  className="rounded-lg p-5 flex items-center gap-2"
                  style={{ border: "1px solid var(--color-border)", background: "rgba(9,20,34,0.6)" }}
                >
                  <div className="w-1 h-1 rounded-full animate-pulse" style={{ background: "var(--color-accent)" }} />
                  <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>
                    Loading clip…
                  </span>
                </div>
              ) : clip?.processing_status === "processing" ? (
                <ProcessingPanel />
              ) : clip?.processing_status === "error" ? (
                <ErrorPanel
                  message={clip.processing_error}
                  onRetry={onReprocess ? handleReprocess : undefined}
                  busy={reprocessing}
                />
              ) : clip?.processed_at == null ? (
                <ProcessCtaPanel
                  onProcess={onReprocess ? handleReprocess : undefined}
                  busy={reprocessing}
                />
              ) : (
                <div
                  className="rounded-lg overflow-hidden"
                  style={{ border: "1px solid var(--color-border)", background: "rgba(9,20,34,0.6)" }}
                >
                  <div
                    className="px-4 py-2.5 flex items-center justify-between"
                    style={{
                      borderBottom: "1px solid var(--color-border)",
                      background: "rgba(12,25,40,0.8)",
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="font-mono text-[9px] px-1.5 py-0.5 uppercase tracking-[0.2em]"
                        style={{
                          background: "rgba(34,211,238,0.08)",
                          color: "var(--color-accent)",
                          border: "1px solid rgba(34,211,238,0.25)",
                          borderRadius: 3,
                        }}
                      >
                        AI
                      </span>
                      <span className="section-label">Analysis</span>
                    </div>
                  </div>
                  <div className="p-5">
                    {primaryExplanation ? (
                      <AiAnalysisText text={primaryExplanation} />
                    ) : hasAnomalies ? (
                      <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>
                        {anomalies.length} anomaly event{anomalies.length === 1 ? "" : "s"} detected, but no AI
                        narrative was generated for this clip. Re-process to attach explanations.
                      </p>
                    ) : (
                      <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
                        This clip shows routine, uneventful driving &mdash; no unsafe events flagged. No deduction
                        applied to the driver&rsquo;s score.
                      </p>
                    )}

                    {anomalies.length > 1 && (
                      <div className="mt-5">
                        <div
                          className="flex items-center justify-between mb-2"
                        >
                          <span
                            className="font-mono text-[10px] uppercase tracking-[0.18em]"
                            style={{ color: "var(--color-ink-tertiary)" }}
                          >
                            All detections · {anomalies.length}
                          </span>
                          <span
                            className="font-mono text-[9px] uppercase tracking-[0.18em]"
                            style={{ color: "var(--color-ink-tertiary)" }}
                          >
                            scroll to see more ↓
                          </span>
                        </div>
                        <div
                          className="clip-review-scroll flex flex-col gap-2 pr-2"
                          style={{
                            maxHeight: 240,
                            overflowY: "auto",
                            borderTop: "1px dashed rgba(34,211,238,0.15)",
                            borderBottom: "1px dashed rgba(34,211,238,0.15)",
                            paddingTop: 10,
                            paddingBottom: 10,
                          }}
                        >
                          {anomalies.map((a, i) => (
                            <AnomalyRow key={a.id} anomaly={a} index={i + 1} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* ── Footer ────────────────────────────────────────────────── */}
            <div
              className="px-7 py-4 flex items-center justify-between"
              style={{ borderTop: "1px solid rgba(34,211,238,0.1)", background: "rgba(7,16,30,0.5)" }}
            >
              <div className="font-mono text-[9px] uppercase tracking-[0.2em]" style={{ color: "var(--color-ink-tertiary)" }}>
                <span style={{ color: "var(--color-accent)" }}>▸</span> Press <kbd style={kbd}>ESC</kbd> to close · <kbd style={kbd}>SPACE</kbd> to play / pause
              </div>
              {onReprocess && clip?.processed_at != null && clip?.processing_status === "done" && (
                <button
                  onClick={handleReprocess}
                  disabled={reprocessing}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all"
                  style={{
                    background: reprocessing ? "rgba(34,211,238,0.05)" : "rgba(34,211,238,0.08)",
                    border: "1px solid rgba(34,211,238,0.3)",
                    color: "var(--color-accent)",
                    opacity: reprocessing ? 0.5 : 1,
                    cursor: reprocessing ? "not-allowed" : "pointer",
                  }}
                >
                  <RefreshCw size={11} className={reprocessing ? "animate-spin" : ""} />
                  {reprocessing ? "Re-queuing…" : "Re-process clip"}
                </button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const kbd = {
  padding: "1px 5px",
  fontFamily: "var(--font-mono)",
  fontSize: 9,
  color: "var(--color-ink-secondary)",
  background: "rgba(34,211,238,0.06)",
  border: "1px solid rgba(34,211,238,0.2)",
  borderRadius: 3,
  margin: "0 2px",
} as const;

// ── VerdictCard ───────────────────────────────────────────────────────────────
function VerdictCard({
  hasAnomalies, loading, status, anomalyCount,
}: {
  hasAnomalies: boolean; loading: boolean; status: string; anomalyCount: number;
}) {
  if (loading) {
    return (
      <div
        className="p-5 rounded-lg flex items-center gap-3"
        style={{ background: "rgba(12,25,40,0.6)", border: "1px solid var(--color-border)" }}
      >
        <div
          className="w-2 h-2 rounded-full animate-pulse"
          style={{ background: "var(--color-accent)" }}
        />
        <span className="font-mono text-[11px] uppercase tracking-[0.18em]" style={{ color: "var(--color-ink-secondary)" }}>
          Reading verdict…
        </span>
      </div>
    );
  }

  if (status === "pending") {
    return (
      <div
        className="p-5 rounded-lg"
        style={{ background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.25)" }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Clock size={12} style={{ color: "#F59E0B" }} />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "#F59E0B" }}>
            Awaiting processing
          </span>
        </div>
        <div className="text-display" style={{ fontSize: "1.5rem", lineHeight: 1.1, color: "#F59E0B" }}>
          Not yet analyzed
        </div>
        <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>
          Kick off processing to run the clip through all three detection models.
        </p>
      </div>
    );
  }

  if (hasAnomalies) {
    return (
      <div
        className="p-5 rounded-lg relative overflow-hidden"
        style={{
          background: "linear-gradient(145deg, rgba(244,63,94,0.12) 0%, rgba(244,63,94,0.04) 100%)",
          border: "1px solid rgba(244,63,94,0.35)",
        }}
      >
        <div
          className="absolute top-0 right-0 w-32 h-32 pointer-events-none"
          style={{
            background: "radial-gradient(circle, rgba(244,63,94,0.2) 0%, transparent 65%)",
            transform: "translate(30%, -30%)",
          }}
        />
        <div className="flex items-center gap-2 mb-2 relative">
          <AlertTriangle size={12} style={{ color: "#F43F5E" }} />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "#F43F5E" }}>
            Verdict
          </span>
        </div>
        <div
          className="text-display relative"
          style={{ fontSize: "1.75rem", lineHeight: 1.05, color: "#F43F5E", letterSpacing: "-0.02em" }}
        >
          Anomaly Detected
        </div>
        <p className="mt-2 text-[11px] leading-relaxed relative" style={{ color: "#FCA5A5" }}>
          {anomalyCount} event{anomalyCount === 1 ? "" : "s"} flagged across the detection stack.
        </p>
      </div>
    );
  }

  return (
    <div
      className="p-5 rounded-lg relative overflow-hidden"
      style={{
        background: "linear-gradient(145deg, rgba(16,185,129,0.1) 0%, rgba(16,185,129,0.02) 100%)",
        border: "1px solid rgba(16,185,129,0.3)",
      }}
    >
      <div
        className="absolute top-0 right-0 w-32 h-32 pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(16,185,129,0.18) 0%, transparent 65%)",
          transform: "translate(30%, -30%)",
        }}
      />
      <div className="flex items-center gap-2 mb-2 relative">
        <ShieldCheck size={12} style={{ color: "#10B981" }} />
        <span className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "#10B981" }}>
          Verdict
        </span>
      </div>
      <div
        className="text-display relative"
        style={{ fontSize: "1.75rem", lineHeight: 1.05, color: "#10B981", letterSpacing: "-0.02em" }}
      >
        No Anomaly Detected
      </div>
      <p className="mt-2 text-[11px] leading-relaxed relative" style={{ color: "#86EFAC" }}>
        All three models agree: clean driving across this clip.
      </p>
    </div>
  );
}

// ── AnomalyRow ────────────────────────────────────────────────────────────────
// Two stacked lines. Line 1: index badge + type label on a block-level div
// that wraps freely (long labels like "AGGRESSIVE LANE CHANGE" never truncate
// or get clipped). Line 2: timestamp + severity readout.
function AnomalyRow({ anomaly, index }: { anomaly: AnomalySummary; index: number }) {
  const severityColor = anomaly.severity >= 0.7 ? "#F43F5E" : anomaly.severity >= 0.4 ? "#F59E0B" : "#22D3EE";
  return (
    <div
      className="py-2 px-3 rounded"
      style={{
        background: "rgba(12,25,40,0.5)",
        border: "1px solid rgba(28,45,68,0.6)",
        minWidth: 0,
        maxWidth: "100%",
      }}
    >
      {/* Line 1 — index + type (type wraps freely) */}
      <div className="flex items-start gap-2.5" style={{ minWidth: 0 }}>
        <div
          className="font-mono text-[10px] font-semibold tabular-nums px-1.5 py-0.5 rounded flex-shrink-0"
          style={{
            background: "rgba(34,211,238,0.08)",
            border: "1px solid rgba(34,211,238,0.2)",
            color: "var(--color-accent)",
          }}
        >
          {String(index).padStart(2, "0")}
        </div>
        <div
          className="font-mono text-[11px] uppercase"
          style={{
            color: severityColor,
            letterSpacing: "0.06em",
            flex: "1 1 0%",
            minWidth: 0,
            whiteSpace: "normal",
            wordBreak: "break-word",
            overflowWrap: "anywhere",
            lineHeight: 1.35,
          }}
        >
          {anomaly.anomaly_type.replace(/_/g, " ")}
        </div>
      </div>
      {/* Line 2 — time + severity */}
      <div className="flex items-center gap-2 flex-wrap mt-1.5" style={{ paddingLeft: 34 }}>
        <span
          className="font-mono text-[10px] tabular-nums flex-shrink-0"
          style={{ color: "var(--color-ink-secondary)" }}
        >
          {secondsToClock(anomaly.timestamp_start)} — {secondsToClock(anomaly.timestamp_end)}
        </span>
        <span
          className="font-mono text-[9px] tabular-nums ml-auto flex-shrink-0"
          style={{ color: severityColor }}
        >
          sev {anomaly.severity.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

// ── ProcessCtaPanel ──────────────────────────────────────────────────────────
// Replaces the AI Analysis panel entirely when a clip hasn't been run yet.
// Spans full width; content isn't boxed into a narrow column.
function ProcessCtaPanel({ onProcess, busy }: { onProcess?: () => void; busy: boolean }) {
  return (
    <div
      className="rounded-lg p-6 flex items-center justify-between gap-6 relative overflow-hidden"
      style={{
        border: "1px solid rgba(245,158,11,0.22)",
        background: "linear-gradient(145deg, rgba(245,158,11,0.06) 0%, rgba(9,20,34,0.6) 100%)",
      }}
    >
      <div
        className="absolute inset-y-0 right-0 w-64 pointer-events-none opacity-60"
        style={{ background: "radial-gradient(ellipse 80% 100% at 100% 50%, rgba(245,158,11,0.08) 0%, transparent 70%)" }}
      />
      <div className="flex-1 min-w-0 relative">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] mb-2" style={{ color: "#F59E0B" }}>
          Not yet analyzed
        </div>
        <p className="text-[13px] leading-relaxed w-full" style={{ color: "var(--color-ink-secondary)" }}>
          This clip has not been run through the detection pipeline. Process it to generate an AI analysis
          describing what happens in the footage and whether anomalies are present.
        </p>
      </div>
      {onProcess && (
        <button
          onClick={onProcess}
          disabled={busy}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-mono text-[11px] uppercase tracking-[0.16em] transition-all flex-shrink-0 relative"
          style={{
            background: busy ? "rgba(34,211,238,0.08)" : "rgba(34,211,238,0.14)",
            border: "1px solid rgba(34,211,238,0.4)",
            color: "var(--color-accent)",
            opacity: busy ? 0.7 : 1,
            cursor: busy ? "not-allowed" : "pointer",
            boxShadow: busy ? "none" : "0 0 18px rgba(34,211,238,0.18)",
          }}
          onMouseEnter={(e) => { if (!busy) e.currentTarget.style.background = "rgba(34,211,238,0.22)"; }}
          onMouseLeave={(e) => { if (!busy) e.currentTarget.style.background = "rgba(34,211,238,0.14)"; }}
        >
          {busy
            ? <><RefreshCw size={12} className="animate-spin" /> Queuing…</>
            : <><Play size={12} /> Process this clip</>}
        </button>
      )}
    </div>
  );
}

// ── ProcessingPanel ──────────────────────────────────────────────────────────
function ProcessingPanel() {
  return (
    <div
      className="rounded-lg p-5 flex items-center gap-4 relative overflow-hidden"
      style={{
        border: "1px solid rgba(34,211,238,0.25)",
        background: "linear-gradient(145deg, rgba(34,211,238,0.06) 0%, rgba(9,20,34,0.6) 100%)",
      }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
        style={{
          background: "rgba(34,211,238,0.12)",
          border: "1px solid rgba(34,211,238,0.4)",
          boxShadow: "0 0 20px rgba(34,211,238,0.25)",
        }}
      >
        <RefreshCw size={16} className="animate-spin" style={{ color: "var(--color-accent)" }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "var(--color-accent)" }}>
          Pipeline running
        </div>
        <p className="text-[12px] mt-1 leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>
          Running feature extraction and the three-model detection stack. The analysis will appear here
          automatically when it finishes.
        </p>
      </div>
    </div>
  );
}

// ── ErrorPanel ───────────────────────────────────────────────────────────────
function ErrorPanel({ message, onRetry, busy }: { message: string | null; onRetry?: () => void; busy: boolean }) {
  return (
    <div
      className="rounded-lg p-5 flex items-center justify-between gap-6 relative overflow-hidden"
      style={{
        border: "1px solid rgba(244,63,94,0.3)",
        background: "linear-gradient(145deg, rgba(244,63,94,0.06) 0%, rgba(9,20,34,0.6) 100%)",
      }}
    >
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] mb-1.5" style={{ color: "#F43F5E" }}>
          Processing failed
        </div>
        <p className="text-[13px] leading-relaxed w-full" style={{ color: "var(--color-ink-secondary)" }}>
          {message ?? "The pipeline raised an error while analyzing this clip."}
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={busy}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all flex-shrink-0"
          style={{
            background: "rgba(244,63,94,0.08)",
            border: "1px solid rgba(244,63,94,0.3)",
            color: "#F43F5E",
            opacity: busy ? 0.6 : 1,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          <RefreshCw size={11} className={busy ? "animate-spin" : ""} />
          {busy ? "Retrying…" : "Retry"}
        </button>
      )}
    </div>
  );
}

// ── AiAnalysisText ────────────────────────────────────────────────────────────
function AiAnalysisText({ text }: { text: string }) {
  // Split into sections — our explainer emits: Explanation \n\n Recommendation \n\n Score-impact
  const parts = text.split("\n\n").filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      {parts.map((p, i) => {
        const recMatch = /^recommendation:\s*/i.exec(p);
        if (recMatch) {
          return (
            <div key={i} className="flex gap-3 pl-3" style={{ borderLeft: "2px solid rgba(34,211,238,0.35)" }}>
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.2em] mb-1" style={{ color: "var(--color-accent)" }}>
                  Recommendation
                </div>
                <p className="text-[12px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
                  {p.slice(recMatch[0].length)}
                </p>
              </div>
            </div>
          );
        }
        // First paragraph = main narrative
        if (i === 0) {
          return (
            <p key={i} className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
              {p}
            </p>
          );
        }
        return (
          <p key={i} className="text-[12px] leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>
            {p}
          </p>
        );
      })}
    </div>
  );
}

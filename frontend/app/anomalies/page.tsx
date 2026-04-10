"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle, Filter, ChevronLeft, ChevronRight, X,
  Play, Pause, Volume2, VolumeX, Camera, Brain, Activity,
  Clock, Zap, TrendingDown, Info,
} from "lucide-react";

import { api, AnomalySummary, AnomalyDetail } from "@/lib/api";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { SeverityBar } from "@/components/ui/SeverityBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatDuration, anomalyLabel, scoreToColor } from "@/lib/utils";

const ANOMALY_TYPES = [
  "hard_braking", "near_miss", "lane_departure", "traffic_violation",
  "tailgating", "aggressive_lane_change", "harsh_cornering", "other",
];
const PAGE_SIZE = 24;

// ── Synced dual video player ───────────────────────────────────────────────────

function SyncedVideoPlayer({
  frontUrl,
  rearUrl,
  startAt = 0,
}: {
  frontUrl: string | null;
  rearUrl: string | null;
  startAt?: number;
}) {
  const frontRef = useRef<HTMLVideoElement>(null);
  const rearRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [currentTime, setCurrentTime] = useState(startAt);
  const [duration, setDuration] = useState(0);
  const syncingRef = useRef(false);

  // Seek both to startAt on mount
  useEffect(() => {
    if (frontRef.current) frontRef.current.currentTime = startAt;
    if (rearRef.current)  rearRef.current.currentTime  = startAt;
    setCurrentTime(startAt);
  }, [startAt]);

  const syncVideos = useCallback((source: "front" | "rear") => {
    if (syncingRef.current) return;
    syncingRef.current = true;
    const src = source === "front" ? frontRef.current : rearRef.current;
    const dst = source === "front" ? rearRef.current  : frontRef.current;
    if (src && dst && Math.abs(src.currentTime - dst.currentTime) > 0.1) {
      dst.currentTime = src.currentTime;
    }
    syncingRef.current = false;
  }, []);

  const togglePlay = () => {
    const f = frontRef.current;
    const r = rearRef.current;
    if (!f && !r) return;
    if (playing) {
      f?.pause(); r?.pause();
    } else {
      f?.play(); r?.play();
    }
    setPlaying(p => !p);
  };

  const handleTimeUpdate = (source: "front" | "rear") => {
    const vid = source === "front" ? frontRef.current : rearRef.current;
    if (vid) {
      setCurrentTime(vid.currentTime);
      syncVideos(source);
    }
  };

  const handleLoadedMetadata = () => {
    const vid = frontRef.current || rearRef.current;
    if (vid) setDuration(vid.duration);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = parseFloat(e.target.value);
    if (frontRef.current) frontRef.current.currentTime = t;
    if (rearRef.current)  rearRef.current.currentTime  = t;
    setCurrentTime(t);
  };

  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;

  const NoVideo = ({ label }: { label: string }) => (
    <div
      className="flex flex-col items-center justify-center h-full gap-2"
      style={{ background: "var(--color-surface)" }}
    >
      <Camera size={22} style={{ color: "var(--color-ink-tertiary)" }} />
      <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>
        {label} unavailable
      </span>
    </div>
  );

  return (
    <div className="space-y-2">
      {/* Dual pane */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { url: frontUrl, label: "Front Camera", ref: frontRef, source: "front" as const },
          { url: rearUrl,  label: "Rear Camera",  ref: rearRef,  source: "rear"  as const },
        ].map(({ url, label, ref, source }) => (
          <div key={label} className="rounded-lg overflow-hidden relative" style={{ background: "#000", aspectRatio: "16/9" }}>
            <div
              className="absolute top-1.5 left-1.5 z-10 font-mono text-[9px] px-1.5 py-0.5 rounded"
              style={{ background: "rgba(7,16,30,0.75)", color: "var(--color-ink-tertiary)", backdropFilter: "blur(4px)" }}
            >
              {label}
            </div>
            {url ? (
              <video
                ref={ref}
                src={url}
                muted={muted}
                playsInline
                className="w-full h-full object-cover"
                onTimeUpdate={() => handleTimeUpdate(source)}
                onLoadedMetadata={handleLoadedMetadata}
                onEnded={() => setPlaying(false)}
              />
            ) : (
              <NoVideo label={label} />
            )}
          </div>
        ))}
      </div>

      {/* Controls */}
      <div
        className="rounded-lg px-3 py-2 flex items-center gap-3"
        style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
      >
        <button
          onClick={togglePlay}
          disabled={!frontUrl && !rearUrl}
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors disabled:opacity-30"
          style={{ background: "var(--color-accent)", color: "#07101E" }}
        >
          {playing ? <Pause size={12} /> : <Play size={12} />}
        </button>

        {/* Timeline scrubber */}
        <div className="flex-1 relative h-1 rounded-full" style={{ background: "var(--color-border)" }}>
          <div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ width: `${pct}%`, background: "var(--color-accent)" }}
          />
          <input
            type="range" min={0} max={duration || 1} step={0.1}
            value={currentTime}
            onChange={handleSeek}
            className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
          />
        </div>

        <span className="font-mono text-[10px] flex-shrink-0" style={{ color: "var(--color-ink-secondary)" }}>
          {formatDuration(currentTime)} / {formatDuration(duration)}
        </span>

        <button
          onClick={() => setMuted(m => !m)}
          className="w-6 h-6 flex items-center justify-center flex-shrink-0"
          style={{ color: "var(--color-ink-tertiary)" }}
        >
          {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
        </button>
      </div>
    </div>
  );
}

// ── Anomaly detail modal ───────────────────────────────────────────────────────

function AnomalyModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [detail, setDetail] = useState<AnomalyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"video" | "ai" | "metadata">("video");

  useEffect(() => {
    api.anomalies.get(id).then(setDetail).catch(() => {}).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const impactColor = detail ? scoreToColor(100 - detail.score_impact * 3) : "#22D3EE";

  const tabs = [
    { id: "video",    label: "Video",      icon: Camera },
    { id: "ai",       label: "AI Analysis",icon: Brain  },
    { id: "metadata", label: "Metadata",   icon: Info   },
  ] as const;

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-8"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    >
      <motion.div
        className="absolute inset-0"
        style={{ background: "rgba(7,16,30,0.88)", backdropFilter: "blur(10px)" }}
        onClick={onClose}
      />
      <motion.div
        className="relative w-full max-w-3xl max-h-[92vh] overflow-y-auto z-10 rounded-xl"
        style={{ background: "var(--color-panel)", border: "1px solid var(--color-border)" }}
        initial={{ scale: 0.96, y: 16 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.96, y: 16 }}
        transition={{ type: "spring", damping: 28, stiffness: 340 }}
      >
        {/* Header */}
        <div
          className="sticky top-0 z-10 px-5 pt-4 pb-3"
          style={{ background: "var(--color-panel)", borderBottom: "1px solid var(--color-border)" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="section-label mb-1.5">Anomaly Detail</p>
              {loading ? (
                <Skeleton className="h-6 w-36" />
              ) : detail ? (
                <AnomalyTypeBadge type={detail.anomaly_type} />
              ) : null}
            </div>
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center rounded-lg flex-shrink-0 transition-colors"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-ink-tertiary)" }}
            >
              <X size={12} />
            </button>
          </div>

          {/* Tabs */}
          {!loading && detail && (
            <div className="flex gap-1 mt-3">
              {tabs.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-md transition-all"
                  style={
                    activeTab === id
                      ? { background: "rgba(34,211,238,0.12)", color: "var(--color-accent)", border: "1px solid rgba(34,211,238,0.25)" }
                      : { color: "var(--color-ink-tertiary)", border: "1px solid transparent" }
                  }
                >
                  <Icon size={10} />
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="p-5">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-48 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : detail ? (
            <>
              {/* Metrics row — always visible */}
              <div className="grid grid-cols-4 gap-2 mb-5">
                {[
                  { label: "Severity",     value: `${Math.round(detail.severity * 100)}%`,    icon: Activity,     color: scoreToColor(100 - detail.severity * 100) },
                  { label: "Confidence",   value: `${Math.round(detail.confidence * 100)}%`,  icon: Zap,          color: "var(--color-accent)" },
                  { label: "Score Impact", value: `−${detail.score_impact.toFixed(1)}`,        icon: TrendingDown, color: "#F43F5E" },
                  { label: "Duration",     value: formatDuration(detail.timestamp_end - detail.timestamp_start), icon: Clock, color: "var(--color-ink-secondary)" },
                ].map(({ label, value, icon: Icon, color }) => (
                  <div
                    key={label}
                    className="text-center py-3 rounded-xl"
                    style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                  >
                    <Icon size={13} className="mx-auto mb-1" style={{ color }} />
                    <p className="text-display font-semibold" style={{ fontSize: "1.15rem", lineHeight: 1.1, color }}>{value}</p>
                    <p className="section-label mt-1">{label}</p>
                  </div>
                ))}
              </div>

              {/* Video Tab */}
              {activeTab === "video" && (
                <div className="space-y-4">
                  <SyncedVideoPlayer
                    frontUrl={detail.front_url}
                    rearUrl={detail.rear_url}
                    startAt={Math.max(0, detail.timestamp_start - 2)}
                  />

                  <div
                    className="rounded-lg p-3 flex items-center gap-3"
                    style={{ background: "rgba(34,211,238,0.04)", border: "1px solid rgba(34,211,238,0.1)" }}
                  >
                    <Clock size={12} style={{ color: "var(--color-accent)", flexShrink: 0 }} />
                    <p className="text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>
                      Anomaly occurs at <span style={{ color: "var(--color-accent)", fontFamily: "var(--font-mono)" }}>T+{detail.timestamp_start.toFixed(1)}s</span>
                      {" "}to <span style={{ color: "var(--color-accent)", fontFamily: "var(--font-mono)" }}>T+{detail.timestamp_end.toFixed(1)}s</span>
                      {" "}— video seeked to 2s before event.
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <p className="section-label">Severity Level</p>
                    <SeverityBar severity={detail.severity} />
                  </div>

                  <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                    {[
                      { k: "Clip",    v: detail.clip_filename ?? "—" },
                      { k: "Model",   v: detail.model_type },
                      { k: "Detected", v: formatDate(detail.detected_at) },
                      { k: "Clip ID", v: String(detail.clip_id).slice(0, 8) + "…" },
                    ].map(({ k, v }) => (
                      <div
                        key={k}
                        className="flex items-center justify-between rounded-lg px-3 py-2"
                        style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                      >
                        <span style={{ color: "var(--color-ink-tertiary)" }}>{k}</span>
                        <span style={{ color: "var(--color-ink-primary)" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Analysis Tab */}
              {activeTab === "ai" && (
                <div className="space-y-4">
                  {detail.ai_explanation ? (
                    <>
                      {/* Parse the stored explanation format: explanation \n\n Recommendation: ... \n\n score_impact_text */}
                      {(() => {
                        const parts = detail.ai_explanation.split(/\n\n/);
                        const mainExplanation = parts[0] ?? "";
                        const recommendationLine = parts.find(p => p.startsWith("Recommendation:")) ?? "";
                        const recommendation = recommendationLine.replace("Recommendation:", "").trim();
                        const scoreImpactText = parts.find(p => !p.startsWith("Recommendation:") && p !== mainExplanation) ?? "";

                        return (
                          <>
                            <div
                              className="rounded-xl p-4"
                              style={{ background: "rgba(34,211,238,0.05)", border: "1px solid rgba(34,211,238,0.2)" }}
                            >
                              <div className="flex items-center gap-2 mb-3">
                                <Brain size={14} style={{ color: "var(--color-accent)" }} />
                                <p className="section-label" style={{ color: "var(--color-accent)" }}>What happened</p>
                              </div>
                              <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
                                {mainExplanation}
                              </p>
                            </div>

                            {recommendation && (
                              <div
                                className="rounded-xl p-4"
                                style={{ background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.2)" }}
                              >
                                <div className="flex items-center gap-2 mb-3">
                                  <Zap size={14} style={{ color: "#10B981" }} />
                                  <p className="section-label" style={{ color: "#10B981" }}>Recommendation</p>
                                </div>
                                <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
                                  {recommendation}
                                </p>
                              </div>
                            )}

                            {scoreImpactText && !scoreImpactText.startsWith("Recommendation:") && (
                              <div
                                className="rounded-xl p-4"
                                style={{ background: `${impactColor}08`, border: `1px solid ${impactColor}25` }}
                              >
                                <div className="flex items-center gap-2 mb-3">
                                  <TrendingDown size={14} style={{ color: impactColor }} />
                                  <p className="section-label" style={{ color: impactColor }}>Score Impact</p>
                                </div>
                                <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-primary)" }}>
                                  {scoreImpactText}
                                </p>
                              </div>
                            )}

                            {/* Score deduction visual */}
                            <div
                              className="rounded-xl p-4"
                              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                            >
                              <p className="section-label mb-3">Score Deduction</p>
                              <div className="flex items-center gap-3">
                                <span className="font-mono text-2xl font-bold" style={{ color: "#F43F5E" }}>
                                  −{detail.score_impact.toFixed(1)}
                                </span>
                                <div className="flex-1">
                                  <div className="h-2 rounded-full" style={{ background: "var(--color-border)" }}>
                                    <div
                                      className="h-full rounded-full transition-all"
                                      style={{
                                        width: `${Math.min(100, detail.score_impact * 3)}%`,
                                        background: "linear-gradient(90deg, #F43F5E, #FF6B6B)",
                                      }}
                                    />
                                  </div>
                                  <p className="font-mono text-[10px] mt-1" style={{ color: "var(--color-ink-tertiary)" }}>
                                    out of 100 point base score
                                  </p>
                                </div>
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </>
                  ) : (
                    <div
                      className="rounded-xl p-8 text-center"
                      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                    >
                      <Brain size={28} className="mx-auto mb-3" style={{ color: "var(--color-ink-tertiary)" }} />
                      <p className="section-label mb-2">No AI explanation available</p>
                      <p className="text-[12px]" style={{ color: "var(--color-ink-secondary)" }}>
                        This clip was processed without AI explanation generation, or the explanation is still pending.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Metadata Tab */}
              {activeTab === "metadata" && (
                <div className="space-y-3">
                  <div
                    className="rounded-xl p-4"
                    style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                  >
                    <p className="section-label mb-3">Detection Metadata</p>
                    {detail.detection_metadata && Object.keys(detail.detection_metadata).length > 0 ? (
                      <div className="space-y-2">
                        {Object.entries(detail.detection_metadata).map(([key, value]) => (
                          <div
                            key={key}
                            className="flex items-center justify-between py-2 px-3 rounded-lg"
                            style={{ background: "var(--color-panel)", border: "1px solid var(--color-border)" }}
                          >
                            <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>
                              {key.replace(/_/g, " ")}
                            </span>
                            <span className="font-mono text-[11px] font-medium" style={{ color: "var(--color-ink-primary)" }}>
                              {typeof value === "number" ? value.toFixed(3) : String(value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[12px]" style={{ color: "var(--color-ink-secondary)" }}>No detection metadata available.</p>
                    )}
                  </div>

                  <div
                    className="rounded-xl p-4"
                    style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                  >
                    <p className="section-label mb-3">Anomaly Record</p>
                    <div className="space-y-2 font-mono text-[11px]">
                      {[
                        { k: "Anomaly ID",    v: String(detail.id) },
                        { k: "Clip ID",       v: String(detail.clip_id) },
                        { k: "Model",         v: detail.model_type },
                        { k: "Type",          v: anomalyLabel(detail.anomaly_type) },
                        { k: "Timestamp",     v: `${detail.timestamp_start.toFixed(2)}s → ${detail.timestamp_end.toFixed(2)}s` },
                        { k: "Detected at",   v: formatDate(detail.detected_at) },
                      ].map(({ k, v }) => (
                        <div
                          key={k}
                          className="flex items-start justify-between gap-4 py-1.5 px-3 rounded-lg"
                          style={{ background: "var(--color-panel)", border: "1px solid var(--color-border)" }}
                        >
                          <span style={{ color: "var(--color-ink-tertiary)", flexShrink: 0 }}>{k}</span>
                          <span style={{ color: "var(--color-ink-secondary)", wordBreak: "break-all", textAlign: "right" }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="py-12 text-center" style={{ color: "var(--color-ink-secondary)" }}>
              Anomaly not found.
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Anomaly card ───────────────────────────────────────────────────────────────

function AnomalyCard({ anomaly, onClick, index }: { anomaly: AnomalySummary; onClick: () => void; index: number }) {
  const impactColor = scoreToColor(100 - anomaly.score_impact * 3);
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.025, duration: 0.35 }}
      onClick={onClick}
      className="panel card-hover cursor-pointer overflow-hidden"
    >
      {/* Thumbnail placeholder */}
      <div
        className="relative h-32 flex items-center justify-center overflow-hidden"
        style={{ background: "var(--color-surface)" }}
      >
        <div className="absolute inset-0 opacity-20"
          style={{ backgroundImage: "linear-gradient(rgba(34,211,238,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.05) 1px, transparent 1px)", backgroundSize: "20px 20px" }}
        />
        <div className="relative z-10 flex flex-col items-center gap-1.5">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(17,31,52,0.8)", border: "1px solid var(--color-border)" }}
          >
            <Camera size={16} style={{ color: "var(--color-ink-tertiary)" }} />
          </div>
          <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>
            {formatDuration(anomaly.timestamp_end - anomaly.timestamp_start)} clip
          </span>
        </div>
        {/* Score impact pill */}
        <div
          className="absolute top-2 right-2 font-mono text-[9px] px-1.5 py-0.5 rounded"
          style={{ background: `${impactColor}18`, border: `1px solid ${impactColor}30`, color: impactColor }}
        >
          −{anomaly.score_impact.toFixed(1)} pts
        </div>
        {/* Timestamp */}
        <div
          className="absolute bottom-2 left-2 font-mono text-[9px] px-1.5 py-0.5 rounded"
          style={{ background: "rgba(7,16,30,0.7)", color: "var(--color-ink-tertiary)" }}
        >
          T+{anomaly.timestamp_start.toFixed(1)}s
        </div>
        {/* AI indicator */}
        {anomaly.ai_explanation && (
          <div
            className="absolute top-2 left-2 w-5 h-5 rounded flex items-center justify-center"
            style={{ background: "rgba(34,211,238,0.15)", border: "1px solid rgba(34,211,238,0.3)" }}
            title="AI explanation available"
          >
            <Brain size={9} style={{ color: "var(--color-accent)" }} />
          </div>
        )}
      </div>

      <div className="p-3.5 space-y-2.5">
        <AnomalyTypeBadge type={anomaly.anomaly_type} size="sm" />
        <SeverityBar severity={anomaly.severity} />
        {anomaly.ai_explanation && (
          <p className="text-[11px] leading-relaxed line-clamp-2" style={{ color: "var(--color-ink-secondary)" }}>
            {anomaly.ai_explanation.split("\n\n")[0]}
          </p>
        )}
        <div
          className="flex items-center justify-between pt-2"
          style={{ borderTop: "1px solid var(--color-border)" }}
        >
          <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)", textTransform: "uppercase" }}>
            {anomaly.model_type}
          </span>
          <span className="font-mono text-[10px] font-medium" style={{ color: "var(--color-accent)" }}>
            conf {Math.round(anomaly.confidence * 100)}%
          </span>
        </div>
      </div>
    </motion.div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<AnomalySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const fetchAnomalies = useCallback(() => {
    setLoading(true);
    api.anomalies
      .list({
        page,
        page_size: PAGE_SIZE,
        anomaly_type: filterType || undefined,
        min_severity: filterSeverity ? parseFloat(filterSeverity) : undefined,
      })
      .then(d => { setAnomalies(d.anomalies); setTotal(d.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, filterType, filterSeverity]);

  useEffect(() => { fetchAnomalies(); }, [fetchAnomalies]);
  useEffect(() => { setPage(1); }, [filterType, filterSeverity]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mb-6"
      >
        <p className="section-label mb-2">Anomaly Detection</p>
        <div className="flex items-end justify-between">
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>
            Anomaly Explorer
          </h1>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>
            {total} events
          </span>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="panel p-4 mb-6"
      >
        <div className="flex flex-wrap gap-3 items-center">
          <Filter size={13} style={{ color: "var(--color-accent)", flexShrink: 0 }} />
          <p className="section-label">Filter</p>
          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            className="panel-sm font-mono text-[11px] px-3 py-1.5"
            style={{ color: "var(--color-ink-primary)" }}
          >
            <option value="">All Types</option>
            {ANOMALY_TYPES.map(t => (
              <option key={t} value={t}>{anomalyLabel(t)}</option>
            ))}
          </select>
          <select
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value)}
            className="panel-sm font-mono text-[11px] px-3 py-1.5"
            style={{ color: "var(--color-ink-primary)" }}
          >
            <option value="">Any Severity</option>
            <option value="0.8">High (≥80%)</option>
            <option value="0.6">Medium+ (≥60%)</option>
            <option value="0.4">Low+ (≥40%)</option>
          </select>
          {(filterType || filterSeverity) && (
            <button
              onClick={() => { setFilterType(""); setFilterSeverity(""); }}
              className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider"
              style={{ color: "#F43F5E" }}
            >
              <X size={10} /> Clear
            </button>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <Brain size={11} style={{ color: "var(--color-accent)" }} />
            <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>
              = AI explanation
            </span>
          </div>
        </div>
      </motion.div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="panel overflow-hidden">
              <Skeleton className="h-32 w-full rounded-none" style={{ borderRadius: "12px 12px 0 0" }} />
              <div className="p-3.5 space-y-2">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-1.5 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : anomalies.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div
            className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
            style={{ background: "rgba(122,156,192,0.08)", border: "1px solid var(--color-border)" }}
          >
            <AlertTriangle size={24} style={{ color: "var(--color-ink-tertiary)" }} />
          </div>
          <p className="section-label mb-2">No anomalies detected</p>
          <p className="text-[13px] max-w-xs" style={{ color: "var(--color-ink-secondary)" }}>
            Process clips first, or adjust your filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {anomalies.map((a, i) => (
            <AnomalyCard
              key={a.id}
              anomaly={a}
              index={i}
              onClick={() => setSelectedId(a.id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30 transition-colors"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30 transition-colors"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      <AnimatePresence>
        {selectedId && (
          <AnomalyModal id={selectedId} onClose={() => setSelectedId(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

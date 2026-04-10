"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Filter, ChevronLeft, ChevronRight, X } from "lucide-react";

import { api, AnomalySummary, AnomalyDetail } from "@/lib/api";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { SeverityBar } from "@/components/ui/SeverityBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatDuration, anomalyLabel, scoreToColor, cn } from "@/lib/utils";

const ANOMALY_TYPES = [
  "hard_braking", "near_miss", "lane_departure", "traffic_violation",
  "tailgating", "aggressive_lane_change", "harsh_cornering", "other",
];
const PAGE_SIZE = 24;

function AnomalyCard({ anomaly, onClick, index }: { anomaly: AnomalySummary; onClick: () => void; index: number }) {
  const impactColor = scoreToColor(100 - anomaly.score_impact * 2);
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
        className="relative h-32 bg-grid-navy flex items-center justify-center overflow-hidden"
        style={{ background: "var(--color-surface)" }}
      >
        <div className="absolute inset-0 bg-grid-navy opacity-30" />
        <div className="relative z-10 flex flex-col items-center gap-1.5">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(17,31,52,0.8)", border: "1px solid var(--color-border)" }}
          >
            <AlertTriangle size={18} style={{ color: "var(--color-ink-tertiary)" }} />
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
      </div>

      <div className="p-3.5 space-y-2.5">
        <AnomalyTypeBadge type={anomaly.anomaly_type} size="sm" />
        <SeverityBar severity={anomaly.severity} />
        {anomaly.ai_explanation && (
          <p className="text-[11px] leading-relaxed line-clamp-2" style={{ color: "var(--color-ink-secondary)" }}>
            {anomaly.ai_explanation}
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

function AnomalyModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [detail, setDetail] = useState<AnomalyDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.anomalies.get(id).then(setDetail).catch(() => {}).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    >
      <motion.div className="absolute inset-0" style={{ background: "rgba(7,16,30,0.85)", backdropFilter: "blur(8px)" }} onClick={onClose} />
      <motion.div
        className="relative panel w-full max-w-xl max-h-[85vh] overflow-y-auto z-10"
        initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 28, stiffness: 320 }}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-7 h-7 flex items-center justify-center rounded-lg transition-colors"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-ink-tertiary)" }}
        >
          <X size={12} />
        </button>

        {loading ? (
          <div className="p-6 space-y-3">
            <Skeleton className="h-4 w-28" /><Skeleton className="h-6 w-44" /><Skeleton className="h-24 w-full" />
          </div>
        ) : detail ? (
          <div className="p-6 space-y-5">
            <div>
              <p className="section-label mb-2.5">Anomaly Detail</p>
              <AnomalyTypeBadge type={detail.anomaly_type} />
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Severity",    value: `${Math.round(detail.severity * 100)}%`,     color: scoreToColor(100 - detail.severity * 100) },
                { label: "Confidence",  value: `${Math.round(detail.confidence * 100)}%`,   color: "var(--color-accent)" },
                { label: "Score Impact",value: `−${detail.score_impact.toFixed(1)} pts`,    color: "#F43F5E" },
              ].map(m => (
                <div
                  key={m.label}
                  className="text-center py-3 rounded-lg"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                >
                  <p className="section-label mb-1.5">{m.label}</p>
                  <p className="text-display" style={{ fontSize: "1.4rem", lineHeight: 1, color: m.color }}>{m.value}</p>
                </div>
              ))}
            </div>

            <div>
              <p className="section-label mb-2">Severity Level</p>
              <SeverityBar severity={detail.severity} />
            </div>

            <div className="rounded-lg p-4 space-y-2" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <p className="section-label mb-2.5">Clip Context</p>
              <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                <div><span style={{ color: "var(--color-ink-tertiary)" }}>Clip:  </span><span style={{ color: "var(--color-ink-secondary)" }}>{detail.clip_filename ?? "—"}</span></div>
                <div><span style={{ color: "var(--color-ink-tertiary)" }}>Model: </span><span style={{ color: "var(--color-ink-secondary)" }}>{detail.model_type}</span></div>
                <div><span style={{ color: "var(--color-ink-tertiary)" }}>Start: </span><span style={{ color: "var(--color-ink-secondary)" }}>{detail.timestamp_start.toFixed(2)}s</span></div>
                <div><span style={{ color: "var(--color-ink-tertiary)" }}>End:   </span><span style={{ color: "var(--color-ink-secondary)" }}>{detail.timestamp_end.toFixed(2)}s</span></div>
                <div className="col-span-2"><span style={{ color: "var(--color-ink-tertiary)" }}>Detected: </span><span style={{ color: "var(--color-ink-secondary)" }}>{formatDate(detail.detected_at)}</span></div>
              </div>
            </div>

            {detail.ai_explanation && (
              <div
                className="rounded-lg p-4"
                style={{ background: "rgba(34,211,238,0.05)", border: "1px solid rgba(34,211,238,0.15)" }}
              >
                <p className="section-label mb-2" style={{ color: "var(--color-accent)" }}>AI Explanation</p>
                <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>{detail.ai_explanation}</p>
              </div>
            )}

            {detail.front_url && (
              <div>
                <p className="section-label mb-2">Front Camera</p>
                <video src={detail.front_url} controls className="w-full rounded-lg" style={{ maxHeight: "280px", background: "var(--color-surface)" }} />
              </div>
            )}
          </div>
        ) : (
          <div className="p-6 text-center" style={{ color: "var(--color-ink-secondary)" }}>Anomaly not found.</div>
        )}
      </motion.div>
    </motion.div>
  );
}

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
    api.anomalies.list({ page, page_size: PAGE_SIZE, anomaly_type: filterType || undefined, min_severity: filterSeverity ? parseFloat(filterSeverity) : undefined })
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
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6">
        <p className="section-label mb-2">Anomaly Detection</p>
        <div className="flex items-end justify-between">
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>Anomaly Explorer</h1>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>{total} events</span>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} className="panel p-4 mb-6">
        <div className="flex flex-wrap gap-3 items-center">
          <Filter size={13} style={{ color: "var(--color-accent)", flexShrink: 0 }} />
          <p className="section-label">Filter</p>
          <select
            value={filterType} onChange={e => setFilterType(e.target.value)}
            className="panel-sm font-mono text-[11px] px-3 py-1.5"
            style={{ color: "var(--color-ink-primary)" }}
          >
            <option value="">All Types</option>
            {ANOMALY_TYPES.map(t => <option key={t} value={t}>{anomalyLabel(t)}</option>)}
          </select>
          <select
            value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}
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
        </div>
      </motion.div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="panel overflow-hidden">
              <Skeleton className="h-32 w-full rounded-none" style={{ borderRadius: "12px 12px 0 0" }} />
              <div className="p-3.5 space-y-2"><Skeleton className="h-4 w-20" /><Skeleton className="h-1.5 w-full" /><Skeleton className="h-8 w-full" /></div>
            </div>
          ))}
        </div>
      ) : anomalies.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4" style={{ background: "rgba(122,156,192,0.08)", border: "1px solid var(--color-border)" }}>
            <AlertTriangle size={24} style={{ color: "var(--color-ink-tertiary)" }} />
          </div>
          <p className="section-label mb-2">No anomalies detected</p>
          <p className="text-[13px] max-w-xs" style={{ color: "var(--color-ink-secondary)" }}>Process clips first, or adjust your filters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {anomalies.map((a, i) => <AnomalyCard key={a.id} anomaly={a} index={i} onClick={() => setSelectedId(a.id)} />)}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-3">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30 hover:border-muted transition-colors">
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>{page} / {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30 hover:border-muted transition-colors">
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      <AnimatePresence>
        {selectedId && <AnomalyModal id={selectedId} onClose={() => setSelectedId(null)} />}
      </AnimatePresence>
    </div>
  );
}

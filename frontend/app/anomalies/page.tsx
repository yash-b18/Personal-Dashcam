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

// ── Anomaly Card ──────────────────────────────────────────────────────────────
function AnomalyCard({ anomaly, onClick, index }: { anomaly: AnomalySummary; onClick: () => void; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.35 }}
      onClick={onClick}
      className="panel cursor-pointer hover:border-amber-dim transition-all duration-200 group overflow-hidden"
      style={{ borderTopColor: scoreToColor(100 - anomaly.score_impact * 2) }}
    >
      {/* Thumbnail placeholder */}
      <div className="relative h-28 bg-surface flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-40" />
        <div className="relative z-10 flex flex-col items-center gap-1">
          <AlertTriangle size={20} className="text-amber-dim group-hover:text-amber-DEFAULT transition-colors" />
          <span className="font-mono text-[9px] text-ink-tertiary uppercase tracking-widest">
            {formatDuration(anomaly.timestamp_end - anomaly.timestamp_start)} clip
          </span>
        </div>
        {/* Timestamp overlay */}
        <div className="absolute bottom-2 right-2 font-mono text-[9px] text-ink-tertiary bg-void/80 px-1.5 py-0.5 rounded-sm">
          T+{anomaly.timestamp_start.toFixed(1)}s
        </div>
      </div>

      <div className="p-3 space-y-2.5">
        <AnomalyTypeBadge type={anomaly.anomaly_type} size="sm" />

        <SeverityBar severity={anomaly.severity} showLabel />

        {anomaly.ai_explanation && (
          <p className="text-[11px] text-ink-secondary leading-relaxed line-clamp-2">
            {anomaly.ai_explanation}
          </p>
        )}

        <div className="flex items-center justify-between pt-1 border-t border-border">
          <span className="font-mono text-[9px] text-ink-tertiary uppercase">
            {anomaly.model_type}
          </span>
          <span className="font-mono text-[10px]" style={{ color: scoreToColor(100 - anomaly.score_impact * 2) }}>
            -{anomaly.score_impact.toFixed(1)} pts
          </span>
        </div>
      </div>
    </motion.div>
  );
}

// ── Detail modal ──────────────────────────────────────────────────────────────
function AnomalyModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [detail, setDetail] = useState<AnomalyDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.anomalies.get(id)
      .then(setDetail)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center p-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        {/* Backdrop */}
        <motion.div
          className="absolute inset-0 bg-void/90 backdrop-blur-sm"
          onClick={onClose}
        />

        {/* Modal */}
        <motion.div
          className="relative panel panel-accent w-full max-w-2xl max-h-[85vh] overflow-y-auto z-10"
          initial={{ scale: 0.95, y: 20 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.95, y: 20 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
        >
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-7 h-7 flex items-center justify-center rounded-sm bg-surface border border-border text-ink-secondary hover:text-amber-DEFAULT transition-colors"
          >
            <X size={12} />
          </button>

          {loading ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detail ? (
            <div className="p-6 space-y-5">
              {/* Header */}
              <div>
                <p className="section-label mb-2">ANOMALY DETAIL</p>
                <AnomalyTypeBadge type={detail.anomaly_type} />
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "SEVERITY",   value: `${Math.round(detail.severity * 100)}%` },
                  { label: "CONFIDENCE", value: `${Math.round(detail.confidence * 100)}%` },
                  { label: "SCORE IMPACT", value: `-${detail.score_impact.toFixed(1)} pts` },
                ].map(m => (
                  <div key={m.label} className="bg-surface border border-border rounded-sm p-3 text-center">
                    <p className="section-label mb-1">{m.label}</p>
                    <p className="font-display text-xl font-bold text-ink-primary"
                       style={{ fontFamily: "'Barlow Condensed'", fontWeight: 800 }}>
                      {m.value}
                    </p>
                  </div>
                ))}
              </div>

              {/* Severity bar full */}
              <div>
                <p className="section-label mb-2">SEVERITY LEVEL</p>
                <SeverityBar severity={detail.severity} />
              </div>

              {/* Video info */}
              <div className="bg-surface border border-border rounded-sm p-4 space-y-2">
                <p className="section-label mb-2">CLIP CONTEXT</p>
                <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <div><span className="text-ink-tertiary">Clip:  </span><span className="text-ink-secondary">{detail.clip_filename ?? "—"}</span></div>
                  <div><span className="text-ink-tertiary">Model: </span><span className="text-ink-secondary">{detail.model_type}</span></div>
                  <div><span className="text-ink-tertiary">Start: </span><span className="text-ink-secondary">{detail.timestamp_start.toFixed(2)}s</span></div>
                  <div><span className="text-ink-tertiary">End:   </span><span className="text-ink-secondary">{detail.timestamp_end.toFixed(2)}s</span></div>
                  <div className="col-span-2"><span className="text-ink-tertiary">Detected: </span><span className="text-ink-secondary">{formatDate(detail.detected_at)}</span></div>
                </div>
              </div>

              {/* AI Explanation */}
              {detail.ai_explanation && (
                <div className="bg-surface border border-amber-dim/40 rounded-sm p-4">
                  <p className="section-label mb-2">AI EXPLANATION</p>
                  <p className="text-[13px] text-ink-secondary leading-relaxed">{detail.ai_explanation}</p>
                </div>
              )}

              {/* Video player — front */}
              {detail.front_url && (
                <div>
                  <p className="section-label mb-2">FRONT CAMERA</p>
                  <video
                    src={detail.front_url}
                    controls
                    className="w-full rounded-sm bg-surface"
                    style={{ maxHeight: "300px" }}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="p-6 text-center text-ink-secondary">Anomaly not found.</div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
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
    api.anomalies.list({
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

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [filterType, filterSeverity]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mb-6">
        <p className="section-label mb-1">ANOMALY DETECTION</p>
        <div className="flex items-end justify-between">
          <h1 className="font-display text-4xl font-extrabold tracking-wide"
              style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 900, fontSize: "2.5rem", letterSpacing: "0.04em" }}>
            ANOMALY EXPLORER
          </h1>
          <span className="font-mono text-[11px] text-ink-tertiary">{total} events found</span>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
        className="panel p-4 mb-6 flex flex-wrap gap-3 items-center"
      >
        <Filter size={13} className="text-amber-DEFAULT flex-shrink-0" />
        <p className="section-label text-ink-secondary">FILTER</p>

        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
          className="bg-surface border border-border text-ink-primary font-mono text-[11px] px-3 py-1.5 rounded-sm"
        >
          <option value="">All Types</option>
          {ANOMALY_TYPES.map(t => (
            <option key={t} value={t}>{anomalyLabel(t)}</option>
          ))}
        </select>

        <select
          value={filterSeverity}
          onChange={e => setFilterSeverity(e.target.value)}
          className="bg-surface border border-border text-ink-primary font-mono text-[11px] px-3 py-1.5 rounded-sm"
        >
          <option value="">Any Severity</option>
          <option value="0.8">High (≥80%)</option>
          <option value="0.6">Medium+ (≥60%)</option>
          <option value="0.4">Low+ (≥40%)</option>
        </select>

        {(filterType || filterSeverity) && (
          <button
            onClick={() => { setFilterType(""); setFilterSeverity(""); }}
            className="flex items-center gap-1 text-label text-crimson hover:text-red-300 transition-colors"
          >
            <X size={10} /> CLEAR
          </button>
        )}
      </motion.div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="panel overflow-hidden">
              <Skeleton className="h-28 w-full" />
              <div className="p-3 space-y-2">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-2 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : anomalies.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <AlertTriangle size={36} className="text-ink-tertiary mb-4" />
          <p className="section-label mb-2">NO ANOMALIES DETECTED</p>
          <p className="text-data text-ink-secondary max-w-xs">
            Process some clips first, or try adjusting your filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {anomalies.map((a, i) => (
            <AnomalyCard key={a.id} anomaly={a} index={i} onClick={() => setSelectedId(a.id)} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30 hover:border-amber-dim transition-colors"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="font-mono text-[11px] text-ink-secondary">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="w-8 h-8 flex items-center justify-center panel rounded-sm disabled:opacity-30 hover:border-amber-dim transition-colors"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Detail Modal */}
      {selectedId && (
        <AnomalyModal id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

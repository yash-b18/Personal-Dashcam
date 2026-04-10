"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import {
  AlertTriangle, TrendingUp, Film, ChevronRight, Activity,
  RefreshCw, ChevronLeft, Zap,
} from "lucide-react";

import { api, DashboardResponse, AnomalyBreakdown, AnomalySummary, ClipScoreHistory } from "@/lib/api";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { SeverityBar } from "@/components/ui/SeverityBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateShort, formatDate, scoreToColor, anomalyLabel, cn } from "@/lib/utils";
import Link from "next/link";

const TYPE_COLORS: Record<string, string> = {
  hard_braking:           "#F43F5E",
  near_miss:              "#FB7185",
  lane_departure:         "#F59E0B",
  traffic_violation:      "#F87171",
  tailgating:             "#F97316",
  aggressive_lane_change: "#EAB308",
  harsh_cornering:        "#22D3EE",
  other:                  "#3D5A80",
};

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, icon: Icon, color, delay = 0 }: {
  label: string; value: string | number; icon: React.ElementType; color?: string; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: "easeOut" }}
      className="panel p-5 relative overflow-hidden"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="section-label mb-3">{label}</p>
          <p className="text-display" style={{ fontSize: "2.25rem", lineHeight: 1, color: color ?? "var(--color-ink-primary)" }}>
            {value}
          </p>
        </div>
        <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
             style={{ background: color ? `${color}18` : "rgba(122,156,192,0.08)", border: `1px solid ${color ? `${color}30` : "var(--color-border)"}` }}>
          <Icon size={16} style={{ color: color ?? "var(--color-ink-tertiary)" }} strokeWidth={1.5} />
        </div>
      </div>
      <div className="absolute bottom-0 left-0 right-0 h-px"
           style={{ background: `linear-gradient(90deg, ${color ?? "transparent"}40 0%, transparent 100%)` }} />
    </motion.div>
  );
}

// ── Score tooltip ─────────────────────────────────────────────────────────────
function ScoreTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const score = payload[0].value;
  return (
    <div className="panel-sm px-3 py-2 text-[11px] font-mono">
      <div style={{ color: "var(--color-ink-tertiary)", marginBottom: "2px" }}>{label}</div>
      <div style={{ color: scoreToColor(score), fontWeight: 600 }}>{score.toFixed(1)}</div>
    </div>
  );
}

// ── Anomaly incident card ─────────────────────────────────────────────────────
function IncidentCard({ anomaly, index }: { anomaly: AnomalySummary; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06, duration: 0.3 }}
    >
      <Link href="/anomalies" className="block panel card-hover p-4 group" style={{ textDecoration: "none" }}>
        <div className="flex items-start gap-3">
          {/* Severity indicator */}
          <div
            className="w-1 rounded-full flex-shrink-0 mt-0.5"
            style={{
              height: "48px",
              background: scoreToColor(100 - anomaly.score_impact * 3),
              boxShadow: `0 0 6px ${scoreToColor(100 - anomaly.score_impact * 3)}60`,
            }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2 mb-2">
              <AnomalyTypeBadge type={anomaly.anomaly_type} size="sm" />
              <span className="font-mono text-[10px] flex-shrink-0"
                    style={{ color: "#F43F5E" }}>
                −{anomaly.score_impact.toFixed(1)} pts
              </span>
            </div>
            <SeverityBar severity={anomaly.severity} showLabel className="mb-2" />
            {anomaly.ai_explanation ? (
              <p className="text-[11px] leading-relaxed line-clamp-2"
                 style={{ color: "var(--color-ink-secondary)" }}>
                {anomaly.ai_explanation}
              </p>
            ) : (
              <p className="text-[11px]" style={{ color: "var(--color-ink-tertiary)" }}>
                No AI explanation generated yet.
              </p>
            )}
          </div>
          <ChevronRight
            size={12}
            className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity mt-1"
            style={{ color: "var(--color-accent)" }}
          />
        </div>
      </Link>
    </motion.div>
  );
}

// ── Trip history row ──────────────────────────────────────────────────────────
function TripRow({ trip, index }: { trip: ClipScoreHistory; index: number }) {
  const color = scoreToColor(trip.score);
  return (
    <motion.tr
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ delay: index * 0.02, duration: 0.3 }}
      className="row-hover" style={{ borderBottom: "1px solid var(--color-border)" }}
    >
      <td className="py-3 pl-5 pr-3">
        <div className="font-mono text-[11px] truncate max-w-[180px]" style={{ color: "var(--color-ink-primary)" }}>
          {trip.filename_prefix}
        </div>
        <div className="font-mono text-[9px] mt-0.5" style={{ color: "var(--color-ink-tertiary)" }}>
          {formatDateShort(trip.recorded_at)}
        </div>
      </td>
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2">
          <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--color-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${trip.score}%`, background: color }} />
          </div>
          <span className="text-display font-bold" style={{ fontSize: "1.1rem", color, lineHeight: 1 }}>
            {Math.round(trip.score)}
          </span>
          <span className="font-mono text-[10px]" style={{ color }}>{trip.grade}</span>
        </div>
      </td>
      <td className="py-3 pr-4 font-mono text-[11px]" style={{ color: trip.anomaly_count > 0 ? "#F43F5E" : "var(--color-ink-tertiary)" }}>
        {trip.anomaly_count}
      </td>
      <td className="py-3 pr-4 font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>
        {formatDate(trip.calculated_at).split("·")[1]?.trim() ?? "—"}
      </td>
    </motion.tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [topAnomalies, setTopAnomalies] = useState<AnomalySummary[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyData, setHistoryData] = useState<ClipScoreHistory[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [recalcLoading, setRecalcLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const HISTORY_PAGE_SIZE = 10;

  const loadDashboard = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.scores.dashboard(),
      api.anomalies.list({ page_size: 5, min_severity: 0.5 }),
    ])
      .then(([dash, anom]) => {
        setData(dash);
        setTopAnomalies(anom.anomalies);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const loadHistory = useCallback(() => {
    api.scores.history({ page: historyPage, page_size: HISTORY_PAGE_SIZE })
      .then(r => { setHistoryData(r.history); setHistoryTotal(r.total); })
      .catch(() => {});
  }, [historyPage]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);
  useEffect(() => { if (data) loadHistory(); }, [data, loadHistory]);

  const handleRecalculate = async () => {
    setRecalcLoading(true);
    try {
      await api.scores.recalculate();
      loadDashboard();
    } finally {
      setRecalcLoading(false);
    }
  };

  if (loading) return <DashboardSkeleton />;
  if (error || !data) return <ErrorState message={error ?? "Failed to load dashboard"} />;

  const trendData = [...data.score_trend].reverse().map(h => ({
    label: formatDateShort(h.recorded_at),
    score: Math.round(h.score),
  }));

  const donutData = data.anomaly_breakdown.map((b: AnomalyBreakdown) => ({
    name: anomalyLabel(b.anomaly_type),
    value: b.count,
    color: TYPE_COLORS[b.anomaly_type] ?? "#3D5A80",
  }));

  const mainColor = scoreToColor(data.overall_score);
  const historyPages = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));

  return (
    <div className="p-8 max-w-[1400px]">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        className="mb-8 flex items-end justify-between">
        <div>
          <p className="section-label mb-2">Overview</p>
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>Driver Dashboard</h1>
        </div>
        <button
          onClick={handleRecalculate}
          disabled={recalcLoading}
          className="btn-secondary gap-2 disabled:opacity-50"
          title="Recalculate scores from all processed clips"
        >
          <RefreshCw size={13} className={recalcLoading ? "animate-spin" : ""} />
          Recalculate Scores
        </button>
      </motion.div>

      {/* Row 1: gauge + stats + trend */}
      <div className="grid grid-cols-12 gap-5 mb-5">
        {/* Score gauge */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="col-span-12 lg:col-span-4 panel p-6 flex flex-col items-center justify-center relative overflow-hidden"
          style={{ minHeight: "320px" }}
        >
          <div className="absolute inset-0 pointer-events-none"
               style={{ background: `radial-gradient(ellipse at 50% 30%, ${mainColor}12 0%, transparent 65%)` }} />
          <p className="section-label mb-6 self-start w-full">Overall Score</p>
          <ScoreGauge score={Math.round(data.overall_score)} grade={data.grade} size={210} animated />
          <div className="mt-5 grid grid-cols-2 gap-3 w-full">
            {[
              { label: "Trips", value: data.clips_analyzed, color: undefined },
              { label: "Anomalies", value: data.recent_anomaly_count, color: "#F43F5E" },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center py-3 rounded-lg"
                   style={{ background: "rgba(28,45,68,0.5)", border: "1px solid var(--color-border)" }}>
                <p className="section-label mb-1.5">{label}</p>
                <p className="text-display" style={{ fontSize: "1.75rem", lineHeight: 1, color: color ?? "var(--color-ink-primary)" }}>{value}</p>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Stats + trend */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Overall Grade"    value={data.grade}               icon={Activity}      color={mainColor} delay={0.1} />
            <StatCard label="Trips Scored"     value={data.clips_analyzed}      icon={Film}          color="#3B82F6"   delay={0.15} />
            <StatCard label="Recent Anomalies" value={data.recent_anomaly_count} icon={AlertTriangle}
              color={data.recent_anomaly_count > 20 ? "#F43F5E" : "#F59E0B"} delay={0.2} />
          </div>

          {trendData.length > 0 ? (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25, duration: 0.4 }} className="panel p-5 flex-1">
              <p className="section-label mb-4">Score Trend · Last {trendData.length} trips</p>
              <ResponsiveContainer width="100%" height={155}>
                <AreaChart data={trendData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#22D3EE" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#22D3EE" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="label" tick={{ fill: "#3D5A80", fontFamily: "'IBM Plex Mono'", fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: "#3D5A80", fontFamily: "'IBM Plex Mono'", fontSize: 9 }} axisLine={false} tickLine={false} ticks={[0, 25, 50, 75, 100]} />
                  <Tooltip content={<ScoreTooltip />} cursor={{ stroke: "rgba(28,45,68,0.8)", strokeWidth: 1 }} />
                  <Area type="monotone" dataKey="score" stroke="#22D3EE" strokeWidth={1.5}
                    fill="url(#scoreGrad)" dot={false} activeDot={{ r: 3, fill: "#22D3EE", stroke: "transparent" }} />
                </AreaChart>
              </ResponsiveContainer>
            </motion.div>
          ) : (
            <div className="panel p-5 flex-1 flex items-center justify-center" style={{ minHeight: "160px" }}>
              <p className="section-label" style={{ color: "var(--color-ink-tertiary)" }}>Process clips to see score history</p>
            </div>
          )}
        </div>
      </div>

      {/* Row 2: donut + top anomalies */}
      <div className="grid grid-cols-12 gap-5 mb-5">
        {/* Breakdown donut */}
        {donutData.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.4 }} className="col-span-12 md:col-span-5 panel p-5">
            <p className="section-label mb-4">Anomaly Breakdown</p>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={donutData} cx="50%" cy="50%" innerRadius={52} outerRadius={82} paddingAngle={3} dataKey="value" stroke="none">
                  {donutData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Legend iconType="circle" iconSize={6}
                  wrapperStyle={{ fontFamily: "'IBM Plex Mono'", fontSize: "9px", color: "#7A9CC0", letterSpacing: "0.06em" }} />
                <Tooltip
                  contentStyle={{ background: "#111F34", border: "1px solid #1C2D44", borderRadius: "8px", fontFamily: "'IBM Plex Mono'", fontSize: "11px" }}
                  labelStyle={{ color: "#7A9CC0" }} itemStyle={{ color: "#EAF2FF" }} />
              </PieChart>
            </ResponsiveContainer>

            {/* Per-type deduction table */}
            {data.anomaly_breakdown.length > 0 && (
              <div className="mt-3 space-y-1.5" style={{ borderTop: "1px solid var(--color-border)", paddingTop: "12px" }}>
                <p className="section-label mb-2">Score Impact by Type</p>
                {data.anomaly_breakdown.map((b: AnomalyBreakdown) => (
                  <div key={b.anomaly_type} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                           style={{ background: TYPE_COLORS[b.anomaly_type] ?? "#3D5A80" }} />
                      <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-secondary)" }}>
                        {anomalyLabel(b.anomaly_type)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>×{b.count}</span>
                      <span className="font-mono text-[10px]" style={{ color: "#F43F5E" }}>
                        −{b.total_score_impact.toFixed(1)} pts
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* Top anomalies — AI explanations */}
        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.4 }}
          className={cn("panel p-5", donutData.length > 0 ? "col-span-12 md:col-span-7" : "col-span-12")}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap size={13} style={{ color: "#F43F5E" }} />
              <p className="section-label">Notable Incidents</p>
            </div>
            <Link href="/anomalies" className="text-[11px] font-medium flex items-center gap-1"
                  style={{ color: "var(--color-accent)" }}>
              View all <ChevronRight size={10} />
            </Link>
          </div>

          {topAnomalies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8">
              <p className="section-label" style={{ color: "var(--color-ink-tertiary)" }}>No anomalies detected yet</p>
              <p className="text-[12px] mt-1" style={{ color: "var(--color-ink-tertiary)" }}>
                Process clips to generate anomaly detections with AI explanations.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {topAnomalies.map((a, i) => <IncidentCard key={a.id} anomaly={a} index={i} />)}
            </div>
          )}
        </motion.div>
      </div>

      {/* Row 3: Full trip history table */}
      {historyData.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.4 }} className="panel overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4"
               style={{ borderBottom: "1px solid var(--color-border)" }}>
            <p className="section-label">Trip History</p>
            <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-tertiary)" }}>
              {historyTotal} scored trips
            </span>
          </div>
          <table className="w-full">
            <thead>
              <tr style={{ background: "rgba(12,25,40,0.6)", borderBottom: "1px solid var(--color-border)" }}>
                {["Filename / Date", "Score", "Anomalies", "Scored At"].map(h => (
                  <th key={h} className="py-2.5 pl-5 text-left section-label">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {historyData.map((trip, i) => <TripRow key={trip.clip_id} trip={trip} index={i} />)}
            </tbody>
          </table>

          {/* Pagination */}
          {historyPages > 1 && (
            <div className="flex items-center justify-center gap-3 py-4"
                 style={{ borderTop: "1px solid var(--color-border)" }}>
              <button onClick={() => setHistoryPage(p => Math.max(1, p - 1))} disabled={historyPage === 1}
                className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                <ChevronLeft size={14} />
              </button>
              <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-secondary)" }}>
                {historyPage} / {historyPages}
              </span>
              <button onClick={() => setHistoryPage(p => Math.min(historyPages, p + 1))} disabled={historyPage === historyPages}
                className="w-8 h-8 flex items-center justify-center panel-sm disabled:opacity-30">
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

// ── Skeletons / Error ─────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div className="p-8 max-w-[1400px]">
      <div className="mb-8"><Skeleton className="h-4 w-24 mb-2" /><Skeleton className="h-8 w-48" /></div>
      <div className="grid grid-cols-12 gap-5 mb-5">
        <div className="col-span-12 lg:col-span-4 panel p-6 flex items-center justify-center" style={{ minHeight: "320px" }}>
          <Skeleton className="w-44 h-44 rounded-full" />
        </div>
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">
          <div className="grid grid-cols-3 gap-4">{[0,1,2].map(i => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-44" />
        </div>
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="p-8 flex flex-col items-center justify-center min-h-[60vh]">
      <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
           style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)" }}>
        <AlertTriangle size={24} style={{ color: "#F59E0B" }} />
      </div>
      <p className="section-label mb-2" style={{ color: "#F59E0B" }}>Backend Offline</p>
      <p className="text-[13px] text-center max-w-sm" style={{ color: "var(--color-ink-secondary)" }}>{message}</p>
      <p className="font-mono text-[11px] mt-4" style={{ color: "var(--color-ink-tertiary)" }}>
        Run: uvicorn app:app --reload
      </p>
    </div>
  );
}

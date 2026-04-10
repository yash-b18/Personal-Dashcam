"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { AlertTriangle, TrendingUp, Film, ChevronRight, Activity } from "lucide-react";

import { api, DashboardResponse, AnomalyBreakdown } from "@/lib/api";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateShort, scoreToColor, anomalyLabel, cn } from "@/lib/utils";
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

function StatCard({ label, value, icon: Icon, color, delay = 0 }: {
  label: string; value: string | number; icon: React.ElementType; color?: string; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: "easeOut" }}
      className="panel p-5 relative overflow-hidden"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="section-label mb-3">{label}</p>
          <p
            className="text-display"
            style={{ fontSize: "2.25rem", lineHeight: 1, color: color ?? "var(--color-ink-primary)" }}
          >
            {value}
          </p>
        </div>
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: color ? `${color}18` : "rgba(122,156,192,0.08)", border: `1px solid ${color ? `${color}30` : "var(--color-border)"}` }}
        >
          <Icon size={16} style={{ color: color ?? "var(--color-ink-tertiary)" }} strokeWidth={1.5} />
        </div>
      </div>
      {/* Subtle accent line */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{ background: `linear-gradient(90deg, ${color ?? "transparent"}40 0%, transparent 100%)` }}
      />
    </motion.div>
  );
}

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

export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.scores.dashboard()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <div className="p-8 max-w-[1400px]">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-8 flex items-end justify-between"
      >
        <div>
          <p className="section-label mb-2">Overview</p>
          <h1 className="text-display" style={{ fontSize: "2rem", letterSpacing: "-0.02em" }}>
            Driver Dashboard
          </h1>
        </div>
        <Link
          href="/anomalies"
          className="btn-secondary text-[12px] gap-1.5"
          style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "8px 14px", fontSize: "12px" }}
        >
          View Anomalies <ChevronRight size={12} />
        </Link>
      </motion.div>

      <div className="grid grid-cols-12 gap-5">
        {/* Score hero */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="col-span-12 lg:col-span-4 panel p-6 flex flex-col items-center justify-center relative overflow-hidden"
          style={{ minHeight: "320px" }}
        >
          {/* Background radial glow */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: `radial-gradient(ellipse at 50% 30%, ${mainColor}14 0%, transparent 65%)` }}
          />
          <p className="section-label mb-6 self-start w-full">Overall Score</p>
          <ScoreGauge score={Math.round(data.overall_score)} grade={data.grade} size={210} animated />
          <div className="mt-5 grid grid-cols-2 gap-3 w-full">
            <div
              className="text-center py-3 rounded-lg"
              style={{ background: "rgba(28,45,68,0.5)", border: "1px solid var(--color-border)" }}
            >
              <p className="section-label mb-1.5">Trips</p>
              <p className="text-display" style={{ fontSize: "1.75rem", lineHeight: 1 }}>{data.clips_analyzed}</p>
            </div>
            <div
              className="text-center py-3 rounded-lg"
              style={{ background: "rgba(28,45,68,0.5)", border: "1px solid var(--color-border)" }}
            >
              <p className="section-label mb-1.5">Anomalies</p>
              <p className="text-display" style={{ fontSize: "1.75rem", lineHeight: 1, color: "#F43F5E" }}>
                {data.recent_anomaly_count}
              </p>
            </div>
          </div>
        </motion.div>

        {/* Right column */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Overall Grade"    value={data.grade}               icon={Activity}      color={mainColor}   delay={0.1} />
            <StatCard label="Trips Scored"     value={data.clips_analyzed}      icon={Film}          color="#3B82F6"     delay={0.15} />
            <StatCard label="Recent Anomalies" value={data.recent_anomaly_count} icon={AlertTriangle} color={data.recent_anomaly_count > 20 ? "#F43F5E" : "#F59E0B"} delay={0.2} />
          </div>

          {/* Score trend */}
          {trendData.length > 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25, duration: 0.4 }}
              className="panel p-5 flex-1"
            >
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
                  <Area type="monotone" dataKey="score" stroke="#22D3EE" strokeWidth={1.5} fill="url(#scoreGrad)" dot={false} activeDot={{ r: 3, fill: "#22D3EE", stroke: "transparent" }} />
                </AreaChart>
              </ResponsiveContainer>
            </motion.div>
          ) : (
            <div className="panel p-5 flex-1 flex items-center justify-center" style={{ minHeight: "160px" }}>
              <p className="section-label" style={{ color: "var(--color-ink-tertiary)" }}>Process clips to see score history</p>
            </div>
          )}
        </div>

        {/* Anomaly donut */}
        {donutData.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.4 }}
            className="col-span-12 md:col-span-5 panel p-5"
          >
            <p className="section-label mb-4">Anomaly Breakdown</p>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={donutData} cx="50%" cy="50%" innerRadius={52} outerRadius={82} paddingAngle={3} dataKey="value" stroke="none">
                  {donutData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Legend
                  iconType="circle" iconSize={6}
                  wrapperStyle={{ fontFamily: "'IBM Plex Mono'", fontSize: "9px", color: "#7A9CC0", letterSpacing: "0.06em" }}
                />
                <Tooltip
                  contentStyle={{ background: "#111F34", border: "1px solid #1C2D44", borderRadius: "8px", fontFamily: "'IBM Plex Mono'", fontSize: "11px" }}
                  labelStyle={{ color: "#7A9CC0" }} itemStyle={{ color: "#EAF2FF" }}
                />
              </PieChart>
            </ResponsiveContainer>
          </motion.div>
        )}

        {/* Recent trips */}
        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.4 }}
          className={cn("panel p-5", donutData.length > 0 ? "col-span-12 md:col-span-7" : "col-span-12")}
        >
          <div className="flex items-center justify-between mb-4">
            <p className="section-label">Recent Trips</p>
            <Link href="/trips" className="text-[11px] font-medium flex items-center gap-1" style={{ color: "var(--color-accent)" }}>
              All trips <ChevronRight size={10} />
            </Link>
          </div>
          {data.score_trend.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <p className="section-label" style={{ color: "var(--color-ink-tertiary)" }}>No trips processed yet</p>
            </div>
          ) : (
            <ul>
              {data.score_trend.slice(0, 6).map((h, i) => (
                <li key={h.clip_id}>
                  <div className="row-hover flex items-center gap-4 px-3 py-2.5 rounded-lg cursor-pointer">
                    <div className="w-1 h-8 rounded-full flex-shrink-0" style={{ background: scoreToColor(h.score), boxShadow: `0 0 6px ${scoreToColor(h.score)}60` }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] font-medium truncate" style={{ color: "var(--color-ink-primary)" }}>{h.filename_prefix}</div>
                      <div className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>{formatDateShort(h.recorded_at)}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-display" style={{ fontSize: "1.4rem", lineHeight: 1, color: scoreToColor(h.score) }}>
                        {Math.round(h.score)}
                      </div>
                      <div className="font-mono text-[9px]" style={{ color: "var(--color-ink-tertiary)" }}>{h.anomaly_count} anomaly</div>
                    </div>
                  </div>
                  {i < Math.min(data.score_trend.length - 1, 5) && (
                    <div className="mx-3" style={{ borderTop: "1px solid var(--color-border)" }} />
                  )}
                </li>
              ))}
            </ul>
          )}
        </motion.div>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="p-8 max-w-[1400px]">
      <div className="mb-8"><Skeleton className="h-4 w-24 mb-2" /><Skeleton className="h-8 w-48" /></div>
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-4 panel p-6 flex items-center justify-center" style={{ minHeight: "320px" }}>
          <Skeleton className="w-44 h-44 rounded-full" />
        </div>
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">
          <div className="grid grid-cols-3 gap-4">{[0,1,2].map(i => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="p-8 flex flex-col items-center justify-center min-h-[60vh]">
      <div
        className="w-14 h-14 rounded-xl flex items-center justify-center mb-4"
        style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)" }}
      >
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

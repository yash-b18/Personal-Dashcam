"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { AlertTriangle, TrendingUp, Film, Clock, ChevronRight } from "lucide-react";

import { api, DashboardResponse, AnomalyBreakdown } from "@/lib/api";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { AnomalyTypeBadge } from "@/components/ui/AnomalyTypeBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDate, formatDateShort, scoreToColor, anomalyLabel, gradeColor, cn } from "@/lib/utils";
import Link from "next/link";

// ── Anomaly donut colors ──────────────────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  hard_braking:           "#EF4444",
  near_miss:              "#DC2626",
  lane_departure:         "#F59E0B",
  traffic_violation:      "#F87171",
  tailgating:             "#F97316",
  aggressive_lane_change: "#EAB308",
  harsh_cornering:        "#3B82F6",
  other:                  "#555568",
};

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({
  label,
  value,
  icon: Icon,
  accent,
  delay = 0,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  accent?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: "easeOut" }}
      className="panel panel-accent p-5 relative overflow-hidden"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="section-label mb-2">{label}</p>
          <p
            className="font-display text-4xl font-extrabold leading-none"
            style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, color: accent ?? "var(--color-ink-primary)" }}
          >
            {value}
          </p>
        </div>
        <div className="w-9 h-9 rounded-sm bg-surface border border-border flex items-center justify-center flex-shrink-0">
          <Icon size={16} style={{ color: accent ?? "var(--color-ink-secondary)" }} strokeWidth={1.5} />
        </div>
      </div>
      {/* Decorative corner */}
      <div
        className="absolute bottom-0 right-0 w-16 h-16 opacity-5 rounded-tl-full"
        style={{ background: accent ?? "var(--color-border)" }}
      />
    </motion.div>
  );
}

// ── Custom tooltip for area chart ─────────────────────────────────────────────
function ScoreTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const score = payload[0].value;
  return (
    <div className="panel px-3 py-2 text-[11px] font-mono">
      <div className="text-ink-tertiary mb-0.5">{label}</div>
      <div style={{ color: scoreToColor(score) }} className="font-semibold">{score.toFixed(1)}</div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
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
    color: TYPE_COLORS[b.anomaly_type] ?? "#555568",
  }));

  return (
    <div className="p-8 max-w-[1400px]">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-8"
      >
        <p className="section-label mb-1">REAL-TIME MONITORING</p>
        <h1
          className="text-4xl font-extrabold tracking-wide text-ink-primary"
          style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 900, fontSize: "2.5rem", letterSpacing: "0.04em" }}
        >
          DRIVER DASHBOARD
        </h1>
      </motion.div>

      {/* Main grid */}
      <div className="grid grid-cols-12 gap-5">

        {/* Score gauge hero — left column */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="col-span-12 lg:col-span-4 panel panel-accent p-6 flex flex-col items-center justify-center relative overflow-hidden"
        >
          {/* Background glow */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: `radial-gradient(ellipse at 50% 40%, ${scoreToColor(data.overall_score)}18 0%, transparent 65%)` }}
          />
          <p className="section-label mb-6 self-start">OVERALL SCORE</p>
          <ScoreGauge score={Math.round(data.overall_score)} grade={data.grade} size={220} animated />
          <div className="mt-6 grid grid-cols-2 gap-4 w-full">
            <div className="text-center">
              <p className="section-label mb-1">TRIPS ANALYZED</p>
              <p className="font-display text-3xl font-extrabold text-ink-primary"
                 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800 }}>
                {data.clips_analyzed}
              </p>
            </div>
            <div className="text-center">
              <p className="section-label mb-1">ANOMALIES FOUND</p>
              <p className="font-display text-3xl font-extrabold text-crimson"
                 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 800, color: "#EF4444" }}>
                {data.recent_anomaly_count}
              </p>
            </div>
          </div>
        </motion.div>

        {/* Right column: stats + charts */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">

          {/* Stat cards */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard
              label="OVERALL GRADE"
              value={data.grade}
              icon={TrendingUp}
              accent={scoreToColor(data.overall_score)}
              delay={0.1}
            />
            <StatCard
              label="TRIPS SCORED"
              value={data.clips_analyzed}
              icon={Film}
              accent="var(--color-sapphire)"
              delay={0.15}
            />
            <StatCard
              label="ANOMALIES (RECENT)"
              value={data.recent_anomaly_count}
              icon={AlertTriangle}
              accent={data.recent_anomaly_count > 20 ? "#EF4444" : "#F59E0B"}
              delay={0.2}
            />
          </div>

          {/* Score trend chart */}
          {trendData.length > 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25, duration: 0.4 }}
              className="panel p-5 flex-1"
            >
              <p className="section-label mb-4">SCORE TREND · LAST {trendData.length} TRIPS</p>
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={trendData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#F59E0B" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#F59E0B" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "#555568", fontFamily: "'IBM Plex Mono'", fontSize: 9 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fill: "#555568", fontFamily: "'IBM Plex Mono'", fontSize: 9 }}
                    axisLine={false}
                    tickLine={false}
                    ticks={[0, 25, 50, 75, 100]}
                  />
                  <Tooltip content={<ScoreTooltip />} cursor={{ stroke: "#252530", strokeWidth: 1 }} />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="#F59E0B"
                    strokeWidth={1.5}
                    fill="url(#scoreGrad)"
                    dot={false}
                    activeDot={{ r: 3, fill: "#F59E0B", stroke: "transparent" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </motion.div>
          ) : (
            <div className="panel p-5 flex-1 flex items-center justify-center">
              <p className="text-data text-ink-tertiary">No score history yet — process some clips first.</p>
            </div>
          )}
        </div>

        {/* Anomaly breakdown donut */}
        {donutData.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.4 }}
            className="col-span-12 md:col-span-5 panel p-5"
          >
            <p className="section-label mb-4">ANOMALY BREAKDOWN</p>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={donutData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                  dataKey="value"
                  stroke="none"
                >
                  {donutData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Legend
                  iconType="circle"
                  iconSize={6}
                  wrapperStyle={{ fontFamily: "'IBM Plex Mono'", fontSize: "9px", color: "#8888A0", letterSpacing: "0.08em" }}
                />
                <Tooltip
                  contentStyle={{ background: "#17171D", border: "1px solid #252530", borderRadius: "2px", fontFamily: "'IBM Plex Mono'", fontSize: "11px" }}
                  labelStyle={{ color: "#8888A0" }}
                  itemStyle={{ color: "#F0F0F4" }}
                />
              </PieChart>
            </ResponsiveContainer>
          </motion.div>
        )}

        {/* Recent anomalies feed */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.4 }}
          className={cn("panel p-5", donutData.length > 0 ? "col-span-12 md:col-span-7" : "col-span-12")}
        >
          <div className="flex items-center justify-between mb-4">
            <p className="section-label">RECENT ANOMALIES</p>
            <Link href="/anomalies" className="text-label text-amber-DEFAULT hover:text-amber-glow transition-colors flex items-center gap-1">
              VIEW ALL <ChevronRight size={10} />
            </Link>
          </div>
          {data.score_trend.length === 0 ? (
            <p className="text-data text-ink-tertiary py-6 text-center">No anomalies detected yet.</p>
          ) : (
            <ul className="space-y-0">
              {data.score_trend.slice(0, 6).map((h, i) => (
                <li key={h.clip_id}>
                  <Link
                    href={`/trips`}
                    className="row-hover flex items-center gap-4 px-2 py-2.5 rounded-sm"
                  >
                    <div className="w-1 h-8 rounded-full flex-shrink-0" style={{ background: scoreToColor(h.score) }} />
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[11px] text-ink-primary truncate">{h.filename_prefix}</div>
                      <div className="font-mono text-[9px] text-ink-tertiary">{formatDateShort(h.recorded_at)}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="font-display text-lg font-bold leading-none" style={{ fontFamily: "'Barlow Condensed'", color: scoreToColor(h.score) }}>
                        {Math.round(h.score)}
                      </div>
                      <div className="font-mono text-[9px] text-ink-tertiary">{h.anomaly_count} anomaly</div>
                    </div>
                  </Link>
                  {i < Math.min(data.score_trend.length - 1, 5) && (
                    <div className="mx-2 border-t border-border" />
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

// ── Loading state ─────────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div className="p-8 max-w-[1400px]">
      <div className="mb-8">
        <Skeleton className="h-3 w-32 mb-2" />
        <Skeleton className="h-10 w-64" />
      </div>
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-4 panel p-6 flex items-center justify-center h-64">
          <Skeleton className="w-48 h-48 rounded-full" />
        </div>
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-5">
          <div className="grid grid-cols-3 gap-4">
            {[0, 1, 2].map(i => <Skeleton key={i} className="h-24 rounded-sm" />)}
          </div>
          <Skeleton className="h-40 rounded-sm" />
        </div>
      </div>
    </div>
  );
}

// ── Error state ───────────────────────────────────────────────────────────────
function ErrorState({ message }: { message: string }) {
  return (
    <div className="p-8 flex flex-col items-center justify-center min-h-[60vh]">
      <AlertTriangle size={40} className="text-amber-DEFAULT mb-4" />
      <p className="section-label mb-2 text-center">BACKEND OFFLINE</p>
      <p className="text-data text-ink-secondary text-center max-w-sm">{message}</p>
      <p className="text-label text-ink-tertiary mt-4">Start the FastAPI server and refresh.</p>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { scoreToColor } from "@/lib/utils";

interface ScoreGaugeProps {
  score: number;
  grade: string;
  size?: number;
  animated?: boolean;
}

export function ScoreGauge({ score, grade, size = 220, animated = true }: ScoreGaugeProps) {
  const [displayScore, setDisplayScore] = useState(animated ? 0 : score);
  const [progress, setProgress] = useState(animated ? 0 : score);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);

  const DURATION = 1400;
  const RADIUS = 78;
  const STROKE = 12;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  const ARC_DEGREES = 240;
  const ARC = (ARC_DEGREES / 360) * CIRCUMFERENCE;
  const GAP = CIRCUMFERENCE - ARC;
  const color = scoreToColor(score);
  const dashOffset = ARC - (progress / 100) * ARC;
  const cx = size / 2;
  const cy = size / 2;

  useEffect(() => {
    if (!animated) return;
    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(elapsed / DURATION, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = eased * score;
      setDisplayScore(current);
      setProgress(current);
      if (t < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [score, animated]);

  // Show one decimal so a near-perfect score like 99.69 doesn't misleadingly round up to 100.
  const displayText = displayScore >= 100 ? "100" : displayScore.toFixed(1);

  return (
    <div className="relative flex flex-col items-center">
      <svg
        width={size}
        height={size * 0.8}
        viewBox={`0 0 ${size} ${size * 0.8}`}
        className="overflow-visible"
      >
        {/* Outer glow */}
        <circle
          cx={cx} cy={cx} r={RADIUS + STROKE / 2 + 10}
          fill="none" stroke={color} strokeWidth="1" opacity="0.1"
          strokeDasharray={`${ARC} ${GAP}`} strokeDashoffset={-GAP / 2}
          transform={`rotate(150 ${cx} ${cx})`}
        />
        {/* Track */}
        <circle
          cx={cx} cy={cx} r={RADIUS}
          fill="none" stroke="rgba(28,45,68,0.8)" strokeWidth={STROKE}
          strokeDasharray={`${ARC} ${GAP}`} strokeDashoffset={-GAP / 2}
          transform={`rotate(150 ${cx} ${cx})`} strokeLinecap="round"
        />
        {/* Tick marks */}
        {Array.from({ length: 11 }, (_, i) => {
          const angle = 150 + (i / 10) * ARC_DEGREES;
          const rad = (angle * Math.PI) / 180;
          const r1 = RADIUS + STROKE / 2 + 4;
          const r2 = RADIUS + STROKE / 2 + (i % 5 === 0 ? 11 : 6);
          return (
            <line
              key={i}
              x1={cx + r1 * Math.cos(rad)} y1={cx + r1 * Math.sin(rad)}
              x2={cx + r2 * Math.cos(rad)} y2={cx + r2 * Math.sin(rad)}
              stroke={i % 5 === 0 ? "rgba(122,156,192,0.5)" : "rgba(61,90,128,0.4)"}
              strokeWidth={i % 5 === 0 ? 1.5 : 0.75}
            />
          );
        })}
        {/* Progress arc */}
        <circle
          cx={cx} cy={cx} r={RADIUS}
          fill="none" stroke={color} strokeWidth={STROKE}
          strokeDasharray={`${ARC} ${GAP}`}
          strokeDashoffset={-GAP / 2 + dashOffset}
          strokeLinecap="round"
          transform={`rotate(150 ${cx} ${cx})`}
          style={{ filter: `drop-shadow(0 0 10px ${color}80)` }}
        />
        {/* Progress end dot */}
        {(() => {
          const angle = 150 + (progress / 100) * ARC_DEGREES;
          const rad = (angle * Math.PI) / 180;
          return (
            <circle
              cx={cx + RADIUS * Math.cos(rad)}
              cy={cx + RADIUS * Math.sin(rad)}
              r={STROKE / 2 + 2}
              fill={color}
              style={{ filter: `drop-shadow(0 0 8px ${color})` }}
            />
          );
        })()}
        {/* Inner subtle ring */}
        <circle
          cx={cx} cy={cx} r={RADIUS - STROKE - 8}
          fill="none" stroke="rgba(28,45,68,0.4)" strokeWidth="1"
        />

        {/* Score number — slightly smaller when a decimal is showing so it fits */}
        <text
          x={cx} y={cx - 6}
          textAnchor="middle" dominantBaseline="middle"
          fill={color}
          fontFamily="'Plus Jakarta Sans', sans-serif"
          fontSize={size * (displayText.length > 3 ? 0.2 : 0.25)}
          fontWeight={800}
          letterSpacing="-2"
          style={{ filter: `drop-shadow(0 0 16px ${color}60)` }}
        >
          {displayText}
        </text>

        {/* Grade */}
        <text
          x={cx} y={cx + size * 0.16}
          textAnchor="middle" dominantBaseline="middle"
          fill={color}
          fontFamily="'IBM Plex Mono', monospace"
          fontSize={size * 0.065}
          fontWeight={500}
          letterSpacing="4"
          opacity="0.9"
        >
          GRADE  {grade}
        </text>

        {/* Grade threshold labels — A/B/C/D positioned outside the tick marks at their minimum-score angle */}
        {[
          { pos: 60, label: "D", color: "#F97316" },
          { pos: 70, label: "C", color: "#F59E0B" },
          { pos: 80, label: "B", color: "#3B82F6" },
          { pos: 90, label: "A", color: "#10B981" },
        ].map(({ pos, label, color }) => {
          const angle = 150 + (pos / 100) * ARC_DEGREES;
          const rad = (angle * Math.PI) / 180;
          const r = RADIUS + STROKE / 2 + 20;
          return (
            <text
              key={label}
              x={cx + r * Math.cos(rad)}
              y={cx + r * Math.sin(rad)}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={color}
              fontFamily="'IBM Plex Mono', monospace"
              fontSize="10"
              fontWeight={700}
              opacity="0.85"
              style={{ letterSpacing: "0.05em" }}
            >
              {label}
            </text>
          );
        })}

        {/* Min/Max */}
        <text x={cx - RADIUS - STROKE - 6} y={cx + RADIUS * 0.65}
          textAnchor="middle" fill="rgba(61,90,128,0.7)"
          fontFamily="'IBM Plex Mono', monospace" fontSize="9" fontWeight={500}>0</text>
        <text x={cx + RADIUS + STROKE + 6} y={cx + RADIUS * 0.65}
          textAnchor="middle" fill="rgba(61,90,128,0.7)"
          fontFamily="'IBM Plex Mono', monospace" fontSize="9" fontWeight={500}>100</text>
      </svg>
    </div>
  );
}

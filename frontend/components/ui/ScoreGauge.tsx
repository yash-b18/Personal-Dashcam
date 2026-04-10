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
  const RADIUS = 80;
  const STROKE = 10;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  // Arc: 240° sweep starting from 150° (bottom-left), going clockwise
  const ARC_DEGREES = 240;
  const ARC = (ARC_DEGREES / 360) * CIRCUMFERENCE;
  const GAP = CIRCUMFERENCE - ARC;
  const color = scoreToColor(score);
  const dashOffset = ARC - (progress / 100) * ARC;

  useEffect(() => {
    if (!animated) return;

    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(elapsed / DURATION, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      const current = eased * score;
      setDisplayScore(Math.round(current));
      setProgress(current);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [score, animated]);

  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="relative flex flex-col items-center">
      <svg
        width={size}
        height={size * 0.78}
        viewBox={`0 0 ${size} ${size * 0.78}`}
        className="overflow-visible"
      >
        {/* Outer glow ring */}
        <circle
          cx={cx}
          cy={cx}
          r={RADIUS + STROKE / 2 + 8}
          fill="none"
          stroke={color}
          strokeWidth="1"
          opacity="0.12"
          strokeDasharray={`${ARC} ${GAP}`}
          strokeDashoffset={-GAP / 2}
          strokeLinecap="butt"
          transform={`rotate(150 ${cx} ${cx})`}
        />

        {/* Track */}
        <circle
          cx={cx}
          cy={cx}
          r={RADIUS}
          fill="none"
          stroke="#252530"
          strokeWidth={STROKE}
          strokeDasharray={`${ARC} ${GAP}`}
          strokeDashoffset={-GAP / 2}
          strokeLinecap="butt"
          transform={`rotate(150 ${cx} ${cx})`}
        />

        {/* Tick marks */}
        {Array.from({ length: 11 }, (_, i) => {
          const angle = 150 + (i / 10) * ARC_DEGREES;
          const rad = (angle * Math.PI) / 180;
          const r1 = RADIUS + STROKE / 2 + 4;
          const r2 = RADIUS + STROKE / 2 + (i % 5 === 0 ? 10 : 6);
          return (
            <line
              key={i}
              x1={cx + r1 * Math.cos(rad)}
              y1={cx + r1 * Math.sin(rad)}
              x2={cx + r2 * Math.cos(rad)}
              y2={cx + r2 * Math.sin(rad)}
              stroke={i % 5 === 0 ? "#555568" : "#3A3A48"}
              strokeWidth={i % 5 === 0 ? 1.5 : 0.75}
            />
          );
        })}

        {/* Progress arc */}
        <circle
          cx={cx}
          cy={cx}
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeDasharray={`${ARC} ${GAP}`}
          strokeDashoffset={-GAP / 2 + dashOffset}
          strokeLinecap="butt"
          transform={`rotate(150 ${cx} ${cx})`}
          style={{ filter: `drop-shadow(0 0 8px ${color}66)` }}
        />

        {/* Inner glow spot at progress end */}
        {(() => {
          const angle = 150 + (progress / 100) * ARC_DEGREES;
          const rad = (angle * Math.PI) / 180;
          return (
            <circle
              cx={cx + RADIUS * Math.cos(rad)}
              cy={cx + RADIUS * Math.sin(rad)}
              r={STROKE / 2 + 1}
              fill={color}
              style={{ filter: `drop-shadow(0 0 6px ${color})` }}
            />
          );
        })()}

        {/* Center score readout */}
        <text
          x={cx}
          y={cx - 8}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontFamily="'Barlow Condensed', sans-serif"
          fontSize={size * 0.28}
          fontWeight={800}
          letterSpacing="-2"
          style={{ filter: `drop-shadow(0 0 12px ${color}66)` }}
        >
          {displayScore}
        </text>

        {/* Grade badge */}
        <text
          x={cx}
          y={cx + size * 0.175}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontFamily="'IBM Plex Mono', monospace"
          fontSize={size * 0.075}
          fontWeight={600}
          letterSpacing="4"
        >
          GRADE {grade}
        </text>

        {/* Min / Max labels */}
        <text
          x={cx - RADIUS - STROKE - 4}
          y={cx + RADIUS * 0.62}
          textAnchor="middle"
          fill="#555568"
          fontFamily="'IBM Plex Mono', monospace"
          fontSize="9"
          fontWeight={500}
        >
          0
        </text>
        <text
          x={cx + RADIUS + STROKE + 4}
          y={cx + RADIUS * 0.62}
          textAnchor="middle"
          fill="#555568"
          fontFamily="'IBM Plex Mono', monospace"
          fontSize="9"
          fontWeight={500}
        >
          100
        </text>
      </svg>
    </div>
  );
}

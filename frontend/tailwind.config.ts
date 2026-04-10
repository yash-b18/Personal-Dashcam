import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Core palette — Black Box industrial theme
        void:    "#0C0C0E",
        surface: "#111115",
        panel:   "#17171D",
        border:  "#252530",
        muted:   "#3A3A48",
        // Amber warning system
        amber: {
          DEFAULT: "#F59E0B",
          dim:     "#B97A08",
          glow:    "#FCD34D",
          subtle:  "#1A1500",
        },
        // Status colors
        crimson: "#EF4444",
        emerald: "#10B981",
        sapphire: "#3B82F6",
        // Text
        ink: {
          primary:   "#F0F0F4",
          secondary: "#8888A0",
          tertiary:  "#555568",
        },
      },
      fontFamily: {
        display: ["var(--font-barlow-condensed)", "sans-serif"],
        mono:    ["var(--font-ibm-plex-mono)", "monospace"],
        body:    ["var(--font-inter)", "sans-serif"],
      },
      backgroundImage: {
        "grid-void": "linear-gradient(rgba(37,37,48,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(37,37,48,0.3) 1px, transparent 1px)",
        "amber-glow": "radial-gradient(ellipse at center, rgba(245,158,11,0.15) 0%, transparent 70%)",
        "surface-gradient": "linear-gradient(135deg, #17171D 0%, #111115 100%)",
      },
      backgroundSize: {
        "grid-48": "48px 48px",
      },
      boxShadow: {
        "amber-sm":  "0 0 8px rgba(245,158,11,0.3)",
        "amber-md":  "0 0 20px rgba(245,158,11,0.25)",
        "amber-lg":  "0 0 40px rgba(245,158,11,0.2)",
        "panel":     "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(37,37,48,0.8)",
        "crimson-sm": "0 0 8px rgba(239,68,68,0.3)",
        "emerald-sm": "0 0 8px rgba(16,185,129,0.3)",
      },
      animation: {
        "pulse-amber": "pulse-amber 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan-line": "scan-line 3s linear infinite",
        "data-in": "data-in 0.4s ease-out forwards",
        "fade-up": "fade-up 0.5s ease-out forwards",
      },
      keyframes: {
        "pulse-amber": {
          "0%, 100%": { opacity: "1" },
          "50%":       { opacity: "0.4" },
        },
        "scan-line": {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        "data-in": {
          "0%":   { opacity: "0", transform: "translateX(-4px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "fade-up": {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;

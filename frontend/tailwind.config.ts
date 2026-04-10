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
        bg:      "#07101E",
        surface: "#0C1928",
        panel:   "#111F34",
        border:  "#1C2D44",
        muted:   "#2A3F5A",
        // Cyan accent system
        accent: {
          DEFAULT: "#22D3EE",
          dim:     "#0891B2",
          glow:    "#67E8F9",
          subtle:  "#022C3A",
        },
        // Status
        danger:  "#F43F5E",
        success: "#10B981",
        warning: "#F59E0B",
        info:    "#3B82F6",
        // Text
        ink: {
          primary:   "#EAF2FF",
          secondary: "#7A9CC0",
          tertiary:  "#3D5A80",
        },
      },
      fontFamily: {
        sans: ["var(--font-jakarta)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        card:   "12px",
        button: "8px",
        badge:  "6px",
        sm:     "6px",
        DEFAULT:"8px",
        lg:     "12px",
        xl:     "16px",
      },
      boxShadow: {
        "accent-sm": "0 0 12px rgba(34,211,238,0.25)",
        "accent-md": "0 0 24px rgba(34,211,238,0.2)",
        "accent-lg": "0 0 48px rgba(34,211,238,0.15)",
        "card":      "0 1px 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(28,45,68,0.8)",
        "glow-danger":  "0 0 12px rgba(244,63,94,0.3)",
        "glow-success": "0 0 12px rgba(16,185,129,0.3)",
      },
      backgroundImage: {
        "grid-navy": "linear-gradient(rgba(28,45,68,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(28,45,68,0.5) 1px, transparent 1px)",
        "panel-gradient": "linear-gradient(135deg, #111F34 0%, #0C1928 100%)",
        "accent-gradient": "linear-gradient(135deg, #22D3EE 0%, #3B82F6 100%)",
      },
      animation: {
        "fade-up":    "fade-up 0.4s ease-out forwards",
        "fade-in":    "fade-in 0.3s ease-out forwards",
        "slide-in":   "slide-in 0.4s ease-out forwards",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        "glow-pulse": "glow-pulse 3s ease-in-out infinite",
      },
      keyframes: {
        "fade-up":    { "0%": { opacity: "0", transform: "translateY(10px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "fade-in":    { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "slide-in":   { "0%": { opacity: "0", transform: "translateX(-8px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
        "pulse-soft": { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.5" } },
        "glow-pulse": { "0%, 100%": { filter: "drop-shadow(0 0 8px rgba(34,211,238,0.4))" }, "50%": { filter: "drop-shadow(0 0 16px rgba(34,211,238,0.7))" } },
      },
    },
  },
  plugins: [],
};

export default config;

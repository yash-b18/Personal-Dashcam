import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = {
  title: {
    default: "DashcamIQ — Anomaly Detection",
    template: "%s · DashcamIQ",
  },
  description: "Production-grade dashcam anomaly detection and driver scoring platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="flex min-h-screen">
          <Sidebar />
          <main
            className="flex-1 min-h-screen overflow-y-auto"
            style={{ marginLeft: "var(--sidebar-width)" }}
          >
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

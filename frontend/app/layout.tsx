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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@300;400;500;600;700;800;900&family=IBM+Plex+Mono:wght@300;400;500;600&family=Inter:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-void text-ink-primary antialiased">
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

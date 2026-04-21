"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, Upload, FileVideo, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";

import { api } from "@/lib/api";

type UploadState = "idle" | "uploading" | "processing" | "done" | "error";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called after upload + enqueue succeeds so the parent can refetch. */
  onComplete?: (clipId: string) => void;
}

const MAX_MB = 500;
const ACCEPTED = [".mp4", ".mov", ".m4v", ".avi"];

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function UploadModal({ open, onClose, onComplete }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [state, setState] = useState<UploadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Reset when closed
  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setFile(null); setProgress(0); setState("idle"); setError(null); setDragging(false);
      }, 200);
    }
  }, [open]);

  // Esc to close when not uploading
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && state !== "uploading") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, state, onClose]);

  // Lock scroll
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = prev; };
    }
  }, [open]);

  const validate = (f: File): string | null => {
    const ext = "." + (f.name.split(".").pop() ?? "").toLowerCase();
    if (!ACCEPTED.includes(ext)) return `Unsupported format. Accepted: ${ACCEPTED.join(", ")}`;
    if (f.size > MAX_MB * 1024 * 1024) return `File exceeds ${MAX_MB} MB limit`;
    return null;
  };

  const pickFile = (f: File) => {
    const err = validate(f);
    if (err) { setError(err); return; }
    setError(null); setFile(f); setProgress(0); setState("idle");
  };

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  }, []);

  const beginUpload = async () => {
    if (!file) return;
    setState("uploading"); setError(null); setProgress(0);
    try {
      const res = await api.clips.upload(file, (pct) => setProgress(pct));
      setState("processing");
      // Brief settle delay so the user sees the "processing" state transition
      setTimeout(() => {
        setState("done");
        onComplete?.(res.clip_id);
      }, 500);
    } catch (err) {
      setState("error");
      setError((err as Error).message);
    }
  };

  const reset = () => {
    setFile(null); setProgress(0); setState("idle"); setError(null);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="bg"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{
            background: "rgba(4,10,20,0.75)",
            backdropFilter: "blur(10px)",
            WebkitBackdropFilter: "blur(10px)",
          }}
          onClick={() => state !== "uploading" && onClose()}
        >
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-lg overflow-hidden"
            style={{
              background: "linear-gradient(180deg, #0B1726 0%, #091523 100%)",
              border: "1px solid rgba(34,211,238,0.18)",
              borderRadius: 16,
              boxShadow: "0 24px 80px rgba(0,0,0,0.6), 0 0 80px rgba(34,211,238,0.07)",
            }}
          >
            {/* top glow */}
            <div
              className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-70"
              style={{
                background: "radial-gradient(ellipse 80% 100% at 50% 0%, rgba(34,211,238,0.18) 0%, transparent 70%)",
              }}
            />

            {/* Header */}
            <div
              className="relative flex items-center justify-between px-6 py-4"
              style={{ borderBottom: "1px solid rgba(34,211,238,0.12)" }}
            >
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#22D3EE", boxShadow: "0 0 10px #22D3EE" }} />
                <span className="font-mono text-[10px] uppercase tracking-[0.22em]" style={{ color: "var(--color-accent)" }}>
                  Upload Clip
                </span>
              </div>
              <button
                onClick={onClose}
                disabled={state === "uploading"}
                aria-label="Close"
                className="w-8 h-8 flex items-center justify-center rounded-lg transition-all"
                style={{
                  background: "rgba(34,211,238,0.06)",
                  border: "1px solid rgba(34,211,238,0.2)",
                  color: "var(--color-accent)",
                  opacity: state === "uploading" ? 0.4 : 1,
                  cursor: state === "uploading" ? "not-allowed" : "pointer",
                }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Body */}
            <div className="relative p-6">
              {state === "done" ? (
                <SuccessState onReset={reset} onClose={onClose} />
              ) : (
                <>
                  {/* Drop zone */}
                  <div
                    onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    onClick={() => !file && inputRef.current?.click()}
                    className="relative rounded-xl flex flex-col items-center justify-center py-8 px-5 cursor-pointer transition-all overflow-hidden"
                    style={{
                      border: `1px dashed ${dragging ? "rgba(34,211,238,0.7)" : "rgba(34,211,238,0.22)"}`,
                      background: dragging ? "rgba(34,211,238,0.06)" : "rgba(12,25,40,0.4)",
                    }}
                  >
                    {/* scan grid */}
                    <div
                      className="absolute inset-0 pointer-events-none opacity-[0.08]"
                      style={{
                        backgroundImage:
                          "linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)",
                        backgroundSize: "24px 24px",
                      }}
                    />
                    {file ? (
                      <SelectedFileView file={file} onReset={reset} state={state} progress={progress} />
                    ) : (
                      <EmptyDropzone dragging={dragging} />
                    )}
                    <input
                      ref={inputRef}
                      type="file"
                      className="hidden"
                      accept={ACCEPTED.join(",")}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) pickFile(f);
                        e.target.value = "";
                      }}
                    />
                  </div>

                  {/* Format strip */}
                  <div
                    className="mt-3 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.18em]"
                    style={{ color: "var(--color-ink-tertiary)" }}
                  >
                    <span>Accepted: {ACCEPTED.join(" · ")}</span>
                    <span>Max {MAX_MB} MB</span>
                  </div>

                  {/* Error */}
                  {error && (
                    <div
                      className="mt-4 p-3 rounded-lg flex items-start gap-2"
                      style={{ background: "rgba(244,63,94,0.08)", border: "1px solid rgba(244,63,94,0.25)" }}
                    >
                      <AlertTriangle size={13} style={{ color: "#F43F5E", flexShrink: 0, marginTop: 1 }} />
                      <span className="text-[12px] leading-relaxed" style={{ color: "#FCA5A5" }}>{error}</span>
                    </div>
                  )}

                  {/* CTAs */}
                  <div className="mt-5 flex items-center justify-end gap-2">
                    {file && state !== "uploading" && state !== "processing" && (
                      <button
                        onClick={reset}
                        className="px-3.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em] transition-all"
                        style={{
                          background: "transparent",
                          border: "1px solid var(--color-border)",
                          color: "var(--color-ink-secondary)",
                        }}
                      >
                        Choose different file
                      </button>
                    )}
                    <button
                      onClick={beginUpload}
                      disabled={!file || state === "uploading" || state === "processing"}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.18em] transition-all"
                      style={{
                        background: !file ? "rgba(34,211,238,0.04)" : "rgba(34,211,238,0.14)",
                        border: "1px solid rgba(34,211,238,0.4)",
                        color: "var(--color-accent)",
                        opacity: !file ? 0.35 : 1,
                        cursor: !file ? "not-allowed" : "pointer",
                        boxShadow: !file ? "none" : "0 0 20px rgba(34,211,238,0.15)",
                      }}
                    >
                      {state === "uploading" ? (
                        <><RefreshCw size={11} className="animate-spin" /> Uploading… {progress.toFixed(0)}%</>
                      ) : state === "processing" ? (
                        <><RefreshCw size={11} className="animate-spin" /> Queuing…</>
                      ) : (
                        <><Upload size={11} /> Upload &amp; Process</>
                      )}
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Footer tagline */}
            <div
              className="px-6 py-3 font-mono text-[9px] uppercase tracking-[0.2em]"
              style={{
                borderTop: "1px solid rgba(34,211,238,0.1)",
                background: "rgba(7,16,30,0.5)",
                color: "var(--color-ink-tertiary)",
              }}
            >
              <span style={{ color: "var(--color-accent)" }}>▸</span> Uploaded clips auto-run through the three-model pipeline and contribute to your driver score.
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function EmptyDropzone({ dragging }: { dragging: boolean }) {
  return (
    <div className="relative flex flex-col items-center gap-3 text-center">
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center"
        style={{
          background: "rgba(34,211,238,0.08)",
          border: "1px solid rgba(34,211,238,0.3)",
          boxShadow: dragging ? "0 0 24px rgba(34,211,238,0.35)" : "none",
          transition: "box-shadow 200ms",
        }}
      >
        <Upload size={22} style={{ color: "var(--color-accent)" }} />
      </div>
      <div>
        <div
          className="text-display text-[1.15rem] leading-tight"
          style={{ color: "var(--color-ink-primary)", letterSpacing: "-0.01em" }}
        >
          {dragging ? "Release to add clip" : "Drag a clip here"}
        </div>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: "var(--color-ink-tertiary)" }}>
          or <span style={{ color: "var(--color-accent)" }}>click to browse</span>
        </div>
      </div>
    </div>
  );
}

function SelectedFileView({
  file, onReset, state, progress,
}: {
  file: File; onReset: () => void; state: UploadState; progress: number;
}) {
  return (
    <div className="relative w-full flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{
            background: "rgba(34,211,238,0.08)",
            border: "1px solid rgba(34,211,238,0.3)",
          }}
        >
          <FileVideo size={18} style={{ color: "var(--color-accent)" }} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium truncate" style={{ color: "var(--color-ink-primary)" }}>
            {file.name}
          </div>
          <div className="font-mono text-[10px] mt-0.5 flex items-center gap-2" style={{ color: "var(--color-ink-tertiary)" }}>
            <span>{formatBytes(file.size)}</span>
            {state !== "idle" && (
              <>
                <span>·</span>
                <span style={{ color: state === "error" ? "#F43F5E" : "var(--color-accent)" }}>
                  {state === "uploading" ? `Uploading ${progress.toFixed(0)}%`
                    : state === "processing" ? "Queuing for processing"
                    : state === "error" ? "Upload failed"
                    : "Ready"}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {(state === "uploading" || state === "processing") && (
        <div className="h-1 rounded-full overflow-hidden" style={{ background: "rgba(28,45,68,0.8)" }}>
          <motion.div
            className="h-full"
            style={{
              background: "linear-gradient(90deg, #22D3EE, #3B82F6)",
              boxShadow: "0 0 8px rgba(34,211,238,0.5)",
            }}
            animate={{ width: state === "processing" ? "100%" : `${progress}%` }}
            transition={{ duration: 0.2 }}
          />
        </div>
      )}
    </div>
  );
}

function SuccessState({ onReset, onClose }: { onReset: () => void; onClose: () => void }) {
  return (
    <div className="flex flex-col items-center text-center gap-3 py-2">
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center"
        style={{
          background: "rgba(16,185,129,0.1)",
          border: "1px solid rgba(16,185,129,0.4)",
          boxShadow: "0 0 24px rgba(16,185,129,0.2)",
        }}
      >
        <CheckCircle2 size={22} style={{ color: "#10B981" }} />
      </div>
      <div className="text-display text-[1.4rem]" style={{ color: "#10B981", letterSpacing: "-0.02em" }}>
        Uploaded
      </div>
      <p className="text-[12px] max-w-xs leading-relaxed" style={{ color: "var(--color-ink-secondary)" }}>
        Your clip is in the queue. The three-model pipeline will analyze it and update your driver score shortly.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={onReset}
          className="px-3.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em]"
          style={{
            border: "1px solid var(--color-border)",
            color: "var(--color-ink-secondary)",
          }}
        >
          Upload another
        </button>
        <button
          onClick={onClose}
          className="px-3.5 py-2 rounded-lg font-mono text-[10px] uppercase tracking-[0.16em]"
          style={{
            background: "rgba(34,211,238,0.14)",
            border: "1px solid rgba(34,211,238,0.4)",
            color: "var(--color-accent)",
          }}
        >
          Done
        </button>
      </div>
    </div>
  );
}

"use client";

import { useRef, useState, CSSProperties } from "react";

/**
 * Renders a still frame from a video URL by loading the video, seeking to
 * `seekTo` seconds, then snapshotting the decoded frame onto a canvas. Once
 * captured, the <video> is unmounted so the browser can free its decoder —
 * the canvas bitmap persists across tab switches, so the thumbnail no longer
 * flashes blank when the tab is backgrounded and restored.
 */
export function VideoThumbnail({
  src,
  seekTo = 0,
  className,
  style,
}: {
  src: string;
  seekTo?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [captured, setCaptured] = useState(false);

  const handleLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    const target = Math.max(0, Math.min(seekTo, (v.duration || seekTo + 1) - 0.05));
    try { v.currentTime = target; } catch { /* ignore */ }
  };

  const handleSeeked = () => {
    const v = videoRef.current;
    const c = canvasRef.current;
    if (!v || !c || !v.videoWidth || !v.videoHeight) return;
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    // Cross-origin video taints the canvas for pixel-readback, but the draw
    // itself still paints the frame — and a tainted canvas renders just fine
    // in the DOM, which is all we need.
    try {
      ctx.drawImage(v, 0, 0);
      setCaptured(true);
    } catch { /* ignore */ }
  };

  return (
    <>
      {!captured && (
        <video
          ref={videoRef}
          src={src}
          muted
          playsInline
          preload="metadata"
          onLoadedMetadata={handleLoadedMetadata}
          onSeeked={handleSeeked}
          className={className}
          style={style}
        />
      )}
      <canvas
        ref={canvasRef}
        className={className}
        style={{ ...style, display: captured ? (style?.display ?? "block") : "none" }}
      />
    </>
  );
}

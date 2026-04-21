"""
Naive baseline anomaly detector — dense optical flow magnitude thresholding.

Algorithm:
  1. Decode video frames using OpenCV
  2. Convert each frame to grayscale
  3. Compute dense optical flow (Farneback) between consecutive frames
  4. Calculate per-frame mean magnitude of the flow field
  5. Slide a window over the magnitude signal:
       - Flag if max magnitude in window > MAGNITUDE_THRESHOLD  (sudden motion)
       - Flag if std dev in window > VARIANCE_THRESHOLD         (erratic motion)
  6. Merge overlapping flagged windows
  7. Return binary anomaly flag, severity score, and timestamped windows

No model training required. Thresholds are intentionally conservative to
maximise recall (prefer false positives over missed anomalies) — the
classical and DL models refine detections downstream.

Severity formula:
  severity = clip(( peak_magnitude - threshold ) / ( 2 * threshold ), 0, 1)

Typical dashcam optical flow magnitudes (empirically observed):
  - Normal highway driving:      2–8  px/frame
  - Normal city driving:         3–10 px/frame
  - Hard braking / near-miss:    15–40 px/frame
  - Camera shake / bumps:        5–12 px/frame
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Tunable thresholds ────────────────────────────────────────────────────────
MAGNITUDE_THRESHOLD: float = 12.0
VARIANCE_THRESHOLD: float = 6.0
WINDOW_SIZE_FRAMES: int = 30  # ~1 second at 30 fps
STEP_SIZE_FRAMES: int = 15  # 50% overlap
MIN_MERGE_GAP_FRAMES: int = 10  # merge windows closer than this

# Farneback parameters tuned for 1080p dashcam footage
_FB_PARAMS = dict(
    pyr_scale=0.5,
    levels=3,
    winsize=15,
    iterations=3,
    poly_n=5,
    poly_sigma=1.2,
    flags=0,
)


@dataclass
class AnomalyWindow:
    """A contiguous segment of frames flagged as anomalous."""

    start_frame: int
    end_frame: int
    start_second: float
    end_second: float
    peak_magnitude: float
    mean_magnitude: float
    magnitude_std: float
    severity: float  # 0.0 – 1.0


@dataclass
class BaselineResult:
    """Result of running the optical flow baseline on a single clip."""

    clip_path: str
    is_anomaly: bool
    severity: float
    anomaly_windows: list[AnomalyWindow] = field(default_factory=list)
    frame_magnitudes: list[float] = field(default_factory=list)
    fps: float = 30.0
    total_frames: int = 0
    error: str | None = None


class OpticalFlowBaseline:
    """
    Rule-based anomaly detector using dense optical flow.

    Designed to be fast (CPU-only, no model loading) and to act as an
    upper-bound recall baseline. False positives are acceptable here —
    they surface candidates for human review in the labeling interface.
    """

    def __init__(
        self,
        magnitude_threshold: float = MAGNITUDE_THRESHOLD,
        variance_threshold: float = VARIANCE_THRESHOLD,
        window_size: int = WINDOW_SIZE_FRAMES,
        step_size: int = STEP_SIZE_FRAMES,
        min_merge_gap: int = MIN_MERGE_GAP_FRAMES,
    ) -> None:
        self.magnitude_threshold = magnitude_threshold
        self.variance_threshold = variance_threshold
        self.window_size = window_size
        self.step_size = step_size
        self.min_merge_gap = min_merge_gap

    # ── Public API ────────────────────────────────────────────────────────────

    def predict(self, video_path: str | Path) -> BaselineResult:
        """
        Run anomaly detection on a single local video file.

        Args:
            video_path: Path to an MP4 file (downloaded from R2).

        Returns:
            BaselineResult with anomaly flag, severity, and timestamped windows.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        try:
            magnitudes, fps = self._compute_flow_magnitudes(video_path)
        except Exception as exc:
            logger.error("Optical flow failed for %s: %s", video_path, exc)
            return BaselineResult(
                clip_path=str(video_path),
                is_anomaly=False,
                severity=0.0,
                error=str(exc),
            )

        if len(magnitudes) == 0:
            return BaselineResult(
                clip_path=str(video_path),
                is_anomaly=False,
                severity=0.0,
                fps=fps,
            )

        raw_windows = self._detect_windows(magnitudes)
        merged = self._merge_windows(raw_windows)
        anomaly_windows = self._to_anomaly_windows(merged, fps)
        overall_severity = max((w.severity for w in anomaly_windows), default=0.0)

        return BaselineResult(
            clip_path=str(video_path),
            is_anomaly=len(anomaly_windows) > 0,
            severity=overall_severity,
            anomaly_windows=anomaly_windows,
            frame_magnitudes=magnitudes.tolist(),
            fps=fps,
            total_frames=len(magnitudes) + 1,
        )

    def predict_batch(self, video_paths: list[str | Path]) -> list[BaselineResult]:
        """
        Run detection on a list of local video files.

        Args:
            video_paths: List of paths to MP4 files.

        Returns:
            List of BaselineResult, one per video, in input order.
        """
        return [self.predict(p) for p in video_paths]

    # ── Core algorithm ────────────────────────────────────────────────────────

    def _compute_flow_magnitudes(self, video_path: Path) -> tuple[np.ndarray, float]:
        """
        Compute per-frame mean optical flow magnitudes via Farneback.

        Downscales frames to 640px wide before computing flow for speed.
        Returns N-1 magnitude values for N input frames.

        Args:
            video_path: Path to local MP4.

        Returns:
            Tuple of (magnitudes array shape (N-1,), fps float).
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV could not open: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        magnitudes: list[float] = []
        prev_gray: np.ndarray | None = None

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Downscale to 640px wide for ~4x speed on 1080p footage
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    frame = cv2.resize(
                        frame,
                        (640, int(h * scale)),
                        interpolation=cv2.INTER_AREA,
                    )

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None, **_FB_PARAMS
                    )
                    fx, fy = flow[..., 0], flow[..., 1]
                    magnitudes.append(float(np.mean(np.sqrt(fx**2 + fy**2))))

                prev_gray = gray
        finally:
            cap.release()

        return np.array(magnitudes, dtype=np.float32), fps

    def _detect_windows(self, magnitudes: np.ndarray) -> list[dict]:
        """
        Slide a window over the magnitude signal and flag anomalous segments.

        A window is flagged if peak > magnitude_threshold OR std > variance_threshold.

        Args:
            magnitudes: Per-frame mean optical flow magnitudes, shape (N,).

        Returns:
            List of raw window dicts with frame indices and stats.
        """
        windows: list[dict] = []
        n = len(magnitudes)

        for start in range(0, n - self.window_size + 1, self.step_size):
            end = start + self.window_size
            window = magnitudes[start:end]
            peak = float(np.max(window))
            mean = float(np.mean(window))
            std = float(np.std(window))

            if peak > self.magnitude_threshold or std > self.variance_threshold:
                windows.append(
                    {
                        "start_frame": start,
                        "end_frame": end,
                        "peak_magnitude": peak,
                        "mean_magnitude": mean,
                        "magnitude_std": std,
                    }
                )

        return windows

    def _merge_windows(self, windows: list[dict]) -> list[dict]:
        """
        Merge flagged windows closer than min_merge_gap frames.

        Prevents a single anomaly event from fragmenting into multiple
        adjacent windows due to the sliding step.

        Args:
            windows: Raw flagged windows in frame order.

        Returns:
            Merged list — fewer, longer windows.
        """
        if not windows:
            return []

        merged: list[dict] = [windows[0].copy()]
        for current in windows[1:]:
            last = merged[-1]
            if current["start_frame"] - last["end_frame"] <= self.min_merge_gap:
                last["end_frame"] = current["end_frame"]
                last["peak_magnitude"] = max(
                    last["peak_magnitude"], current["peak_magnitude"]
                )
                last["mean_magnitude"] = (
                    last["mean_magnitude"] + current["mean_magnitude"]
                ) / 2
                last["magnitude_std"] = max(
                    last["magnitude_std"], current["magnitude_std"]
                )
            else:
                merged.append(current.copy())

        return merged

    def _severity_from_magnitude(self, peak_magnitude: float) -> float:
        """
        Convert peak optical flow magnitude to a 0–1 severity score.

        Linear ramp: 0.0 at threshold, 1.0 at 3× threshold.
        """
        if peak_magnitude <= self.magnitude_threshold:
            return 0.0
        normalized = (peak_magnitude - self.magnitude_threshold) / (
            2.0 * self.magnitude_threshold
        )
        return float(np.clip(normalized, 0.0, 1.0))

    def _to_anomaly_windows(
        self, raw_windows: list[dict], fps: float
    ) -> list[AnomalyWindow]:
        """
        Convert raw frame-indexed dicts to AnomalyWindow dataclasses with timestamps.
        """
        return [
            AnomalyWindow(
                start_frame=w["start_frame"],
                end_frame=w["end_frame"],
                start_second=w["start_frame"] / fps,
                end_second=w["end_frame"] / fps,
                peak_magnitude=w["peak_magnitude"],
                mean_magnitude=w["mean_magnitude"],
                magnitude_std=w["magnitude_std"],
                severity=self._severity_from_magnitude(w["peak_magnitude"]),
            )
            for w in raw_windows
        ]

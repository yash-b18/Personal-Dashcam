"""
Naive baseline anomaly detector — optical flow magnitude thresholding.

Algorithm:
  1. Decode video frames from a clip
  2. Compute dense optical flow (Farneback) between consecutive frames
  3. Calculate per-frame mean magnitude of the flow field
  4. Apply a sliding window: if max magnitude in a window exceeds
     MAGNITUDE_THRESHOLD, or variance spikes above VARIANCE_THRESHOLD,
     flag the window as anomalous
  5. Return anomaly flag, severity score, and flagged timestamp windows

No model training required. Thresholds are calibrated on a held-out
validation set of labeled clips.

Implemented in: feature/naive-baseline
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


# Thresholds calibrated during feature/naive-baseline
MAGNITUDE_THRESHOLD = 15.0     # mean optical flow magnitude (pixels/frame)
VARIANCE_THRESHOLD = 8.0       # std dev spike threshold
WINDOW_SIZE_FRAMES = 30        # ~1 second at 30fps
STEP_SIZE_FRAMES = 15          # 50% overlap


@dataclass
class BaselineResult:
    """Result of running the baseline detector on a single clip."""
    clip_path: str
    is_anomaly: bool
    severity: float                      # 0.0 – 1.0
    anomaly_windows: list[dict] = field(default_factory=list)
    # Each window: {"start_frame": int, "end_frame": int, "max_magnitude": float}
    frame_magnitudes: list[float] = field(default_factory=list)


class OpticalFlowBaseline:
    """
    Rule-based anomaly detector using dense optical flow.

    Implemented in feature/naive-baseline.
    """

    def __init__(
        self,
        magnitude_threshold: float = MAGNITUDE_THRESHOLD,
        variance_threshold: float = VARIANCE_THRESHOLD,
        window_size: int = WINDOW_SIZE_FRAMES,
        step_size: int = STEP_SIZE_FRAMES,
    ) -> None:
        self.magnitude_threshold = magnitude_threshold
        self.variance_threshold = variance_threshold
        self.window_size = window_size
        self.step_size = step_size

    def predict(self, video_path: str | Path) -> BaselineResult:
        """
        Run anomaly detection on a single video file.

        Args:
            video_path: Path to the MP4 video file.

        Returns:
            BaselineResult with anomaly flag, severity, and flagged windows.
        """
        raise NotImplementedError("Implemented in feature/naive-baseline")

    def predict_batch(self, video_paths: list[str | Path]) -> list[BaselineResult]:
        """
        Run detection on a list of video files.

        Args:
            video_paths: List of paths to MP4 files.

        Returns:
            List of BaselineResult, one per video.
        """
        return [self.predict(p) for p in video_paths]

    def _compute_flow_magnitudes(self, video_path: str | Path) -> np.ndarray:
        """
        Extract per-frame optical flow magnitudes from a video.

        Implemented in feature/naive-baseline.
        """
        raise NotImplementedError("Implemented in feature/naive-baseline")

    def _detect_windows(self, magnitudes: np.ndarray) -> list[dict]:
        """
        Slide a window over magnitudes and flag anomalous segments.

        Implemented in feature/naive-baseline.
        """
        raise NotImplementedError("Implemented in feature/naive-baseline")

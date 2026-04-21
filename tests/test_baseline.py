"""
Unit tests for the optical flow baseline anomaly detector.

Tests the window detection and merging logic using synthetic magnitude
arrays — no video files or OpenCV required for these tests.
"""

from pathlib import Path

import numpy as np
import pytest

from scripts.models.baseline import (
    MAGNITUDE_THRESHOLD,
    OpticalFlowBaseline,
    AnomalyWindow,
)


@pytest.fixture()
def detector() -> OpticalFlowBaseline:
    """Return a baseline detector with default thresholds."""
    return OpticalFlowBaseline()


class TestDetectWindows:
    """Tests for _detect_windows using synthetic magnitude arrays."""

    def test_all_normal_no_windows(self, detector: OpticalFlowBaseline) -> None:
        """All-low magnitudes should produce no flagged windows."""
        magnitudes = np.full(100, 3.0, dtype=np.float32)
        windows = detector._detect_windows(magnitudes)
        assert windows == []

    def test_spike_produces_window(self, detector: OpticalFlowBaseline) -> None:
        """A magnitude spike above threshold should flag at least one window."""
        magnitudes = np.full(100, 3.0, dtype=np.float32)
        # Insert a spike in the middle of the first window
        magnitudes[10] = MAGNITUDE_THRESHOLD + 5.0
        windows = detector._detect_windows(magnitudes)
        assert len(windows) >= 1

    def test_window_contains_spike_frame(self, detector: OpticalFlowBaseline) -> None:
        """The flagged window should contain the spike frame."""
        magnitudes = np.full(100, 3.0, dtype=np.float32)
        spike_frame = 20
        magnitudes[spike_frame] = MAGNITUDE_THRESHOLD + 10.0
        windows = detector._detect_windows(magnitudes)
        assert any(
            w["start_frame"] <= spike_frame < w["end_frame"]
            for w in windows
        )

    def test_high_variance_flags_window(self) -> None:
        """High std dev within a window should flag it even without a large peak.

        Uses a detector with a low variance_threshold so we can create a
        realistic std spike (alternating 8.0/1.0 → std ≈ 3.5) that stays
        below the magnitude threshold (12.0) but exceeds variance_threshold (3.0).
        """
        # variance_threshold=3.0 so std≈3.5 triggers the flag; peak=8 < magnitude_threshold=12
        sensitive_detector = OpticalFlowBaseline(
            magnitude_threshold=12.0,
            variance_threshold=3.0,
        )
        magnitudes = np.full(100, 2.0, dtype=np.float32)
        magnitudes[0:30:2] = 8.0   # peak=8 < 12, but std≈3.5 > 3.0
        magnitudes[1:30:2] = 1.0
        windows = sensitive_detector._detect_windows(magnitudes)
        assert len(windows) >= 1

    def test_window_dict_has_required_keys(self, detector: OpticalFlowBaseline) -> None:
        """Every flagged window dict must have the expected keys."""
        magnitudes = np.full(100, 3.0, dtype=np.float32)
        magnitudes[5] = 30.0
        windows = detector._detect_windows(magnitudes)
        required_keys = {"start_frame", "end_frame", "peak_magnitude", "mean_magnitude", "magnitude_std"}
        for w in windows:
            assert required_keys.issubset(w.keys())

    def test_short_signal_no_crash(self, detector: OpticalFlowBaseline) -> None:
        """Magnitude array shorter than window_size should produce no windows."""
        magnitudes = np.array([30.0, 30.0], dtype=np.float32)
        windows = detector._detect_windows(magnitudes)
        assert windows == []


class TestMergeWindows:
    """Tests for _merge_windows."""

    def test_empty_input(self, detector: OpticalFlowBaseline) -> None:
        assert detector._merge_windows([]) == []

    def test_single_window_unchanged(self, detector: OpticalFlowBaseline) -> None:
        w = {"start_frame": 0, "end_frame": 30, "peak_magnitude": 20.0,
             "mean_magnitude": 15.0, "magnitude_std": 3.0}
        result = detector._merge_windows([w])
        assert len(result) == 1
        assert result[0]["end_frame"] == 30

    def test_adjacent_windows_merged(self, detector: OpticalFlowBaseline) -> None:
        """Windows within min_merge_gap frames should merge into one."""
        w1 = {"start_frame": 0,  "end_frame": 30, "peak_magnitude": 20.0,
              "mean_magnitude": 15.0, "magnitude_std": 3.0}
        w2 = {"start_frame": 35, "end_frame": 65, "peak_magnitude": 25.0,
              "mean_magnitude": 18.0, "magnitude_std": 4.0}
        result = detector._merge_windows([w1, w2])
        assert len(result) == 1
        assert result[0]["end_frame"] == 65
        assert result[0]["peak_magnitude"] == 25.0

    def test_distant_windows_not_merged(self, detector: OpticalFlowBaseline) -> None:
        """Windows far apart should remain separate."""
        w1 = {"start_frame": 0,   "end_frame": 30,  "peak_magnitude": 20.0,
              "mean_magnitude": 15.0, "magnitude_std": 3.0}
        w2 = {"start_frame": 200, "end_frame": 230, "peak_magnitude": 22.0,
              "mean_magnitude": 16.0, "magnitude_std": 3.5}
        result = detector._merge_windows([w1, w2])
        assert len(result) == 2


class TestSeverity:
    """Tests for _severity_from_magnitude."""

    def test_below_threshold_is_zero(self, detector: OpticalFlowBaseline) -> None:
        assert detector._severity_from_magnitude(MAGNITUDE_THRESHOLD - 1) == 0.0

    def test_at_threshold_is_zero(self, detector: OpticalFlowBaseline) -> None:
        assert detector._severity_from_magnitude(MAGNITUDE_THRESHOLD) == 0.0

    def test_above_threshold_positive(self, detector: OpticalFlowBaseline) -> None:
        assert detector._severity_from_magnitude(MAGNITUDE_THRESHOLD + 5) > 0.0

    def test_very_high_capped_at_one(self, detector: OpticalFlowBaseline) -> None:
        assert detector._severity_from_magnitude(MAGNITUDE_THRESHOLD * 100) == 1.0

    def test_severity_monotonically_increases(self, detector: OpticalFlowBaseline) -> None:
        values = [MAGNITUDE_THRESHOLD + i for i in range(0, 40, 5)]
        severities = [detector._severity_from_magnitude(v) for v in values]
        assert severities == sorted(severities)


class TestToAnomalyWindows:
    """Tests for _to_anomaly_windows timestamp conversion."""

    def test_timestamps_from_fps(self, detector: OpticalFlowBaseline) -> None:
        raw = [{"start_frame": 0, "end_frame": 30,
                "peak_magnitude": 20.0, "mean_magnitude": 15.0, "magnitude_std": 3.0}]
        fps = 30.0
        windows = detector._to_anomaly_windows(raw, fps)
        assert len(windows) == 1
        assert windows[0].start_second == pytest.approx(0.0)
        assert windows[0].end_second == pytest.approx(1.0)

    def test_returns_anomaly_window_type(self, detector: OpticalFlowBaseline) -> None:
        raw = [{"start_frame": 15, "end_frame": 45,
                "peak_magnitude": 20.0, "mean_magnitude": 15.0, "magnitude_std": 3.0}]
        windows = detector._to_anomaly_windows(raw, fps=30.0)
        assert isinstance(windows[0], AnomalyWindow)

    def test_severity_set_on_window(self, detector: OpticalFlowBaseline) -> None:
        raw = [{"start_frame": 0, "end_frame": 30,
                "peak_magnitude": MAGNITUDE_THRESHOLD + 10, "mean_magnitude": 15.0, "magnitude_std": 3.0}]
        windows = detector._to_anomaly_windows(raw, fps=30.0)
        assert windows[0].severity > 0.0


class TestPredictFileNotFound:
    """Test that predict raises on missing file."""

    def test_missing_file_raises(self, detector: OpticalFlowBaseline) -> None:
        with pytest.raises(FileNotFoundError):
            detector.predict("/nonexistent/path/clip.mp4")

"""
Unit tests for the clip pairing logic.

Tests timestamp extraction and front/rear pairing without any R2 connection.
"""

from datetime import datetime

import pytest

from api.storage.clip_pairer import extract_timestamp, pair_clips


class TestExtractTimestamp:
    """Tests for filename timestamp parsing."""

    def test_yyyymmdd_hhmmss(self) -> None:
        ts = extract_timestamp("dashcam/front/20240101_120000.mp4")
        assert ts == datetime(2024, 1, 1, 12, 0, 0)

    def test_with_underscores(self) -> None:
        ts = extract_timestamp("dashcam/front/2024_01_01_12_00_00.mp4")
        assert ts == datetime(2024, 1, 1, 12, 0, 0)

    def test_with_dashes(self) -> None:
        ts = extract_timestamp("dashcam/front/2024-01-01_12-00-00.mp4")
        assert ts == datetime(2024, 1, 1, 12, 0, 0)

    def test_with_prefix(self) -> None:
        ts = extract_timestamp("dashcam/front/REC_20240315_083045.mp4")
        assert ts == datetime(2024, 3, 15, 8, 30, 45)

    def test_no_timestamp_returns_none(self) -> None:
        assert extract_timestamp("dashcam/front/no_date_here.mp4") is None


def _make_obj(key: str, size: int = 1000) -> dict:
    """Helper to create a minimal R2 object metadata dict."""
    return {"Key": key, "Size": size}


class TestPairClips:
    """Tests for the front/rear pairing algorithm."""

    def test_exact_match(self) -> None:
        front = [_make_obj("main/front/20240101_120000.mp4")]
        rear = [_make_obj("main/rear/20240101_120000.mp4")]
        result = pair_clips(front, rear)
        assert len(result.pairs) == 1
        assert len(result.unmatched_front) == 0
        assert len(result.unmatched_rear) == 0

    def test_within_tolerance(self) -> None:
        """Clips 3 seconds apart should still pair (tolerance = 5s)."""
        front = [_make_obj("main/front/20240101_120000.mp4")]
        rear = [_make_obj("main/rear/20240101_120003.mp4")]
        result = pair_clips(front, rear)
        assert len(result.pairs) == 1

    def test_outside_tolerance(self) -> None:
        """Clips 10 seconds apart should not pair."""
        front = [_make_obj("main/front/20240101_120000.mp4")]
        rear = [_make_obj("main/rear/20240101_120010.mp4")]
        result = pair_clips(front, rear, tolerance_seconds=5)
        assert len(result.pairs) == 0
        assert len(result.unmatched_front) == 1
        assert len(result.unmatched_rear) == 1

    def test_multiple_pairs(self) -> None:
        front = [
            _make_obj("main/front/20240101_120000.mp4"),
            _make_obj("main/front/20240101_120300.mp4"),
            _make_obj("main/front/20240101_120600.mp4"),
        ]
        rear = [
            _make_obj("main/rear/20240101_120000.mp4"),
            _make_obj("main/rear/20240101_120300.mp4"),
            _make_obj("main/rear/20240101_120600.mp4"),
        ]
        result = pair_clips(front, rear)
        assert len(result.pairs) == 3
        assert len(result.unmatched_front) == 0
        assert len(result.unmatched_rear) == 0

    def test_extra_rear_clip_unmatched(self) -> None:
        front = [_make_obj("main/front/20240101_120000.mp4")]
        rear = [
            _make_obj("main/rear/20240101_120000.mp4"),
            _make_obj("main/rear/20240101_130000.mp4"),  # no front match
        ]
        result = pair_clips(front, rear)
        assert len(result.pairs) == 1
        assert len(result.unmatched_rear) == 1

    def test_one_to_one_matching(self) -> None:
        """Each rear clip should only be matched to one front clip."""
        front = [
            _make_obj("main/front/20240101_120000.mp4"),
            _make_obj("main/front/20240101_120001.mp4"),  # 1 second later
        ]
        rear = [_make_obj("main/rear/20240101_120000.mp4")]
        result = pair_clips(front, rear)
        # Only one pair should form — the closer one gets the rear clip
        assert len(result.pairs) == 1
        assert len(result.unmatched_front) == 1

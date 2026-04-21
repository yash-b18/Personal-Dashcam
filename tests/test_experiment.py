"""
Unit tests for the training set size sensitivity experiment.

All tests use synthetic data — no DB, no R2, no video files.
"""

from pathlib import Path

import numpy as np
import pytest

from scripts.experiment import (
    TRAIN_FRACTIONS,
    _compute_metrics,
    _expand_windows,
    _stratified_sample,
    aggregate_results,
)


# ── _stratified_sample ─────────────────────────────────────────────────────────

class TestStratifiedSample:
    def _labels(self, n_pos: int, n_neg: int) -> np.ndarray:
        return np.array([1] * n_pos + [0] * n_neg, dtype=np.int32)

    def test_returns_correct_size(self) -> None:
        y = self._labels(10, 10)
        idx = _stratified_sample(y, 6, seed=0)
        assert len(idx) == 6

    def test_indices_in_range(self) -> None:
        y = self._labels(8, 12)
        idx = _stratified_sample(y, 8, seed=1)
        assert all(0 <= i < len(y) for i in idx)

    def test_no_duplicates(self) -> None:
        y = self._labels(10, 10)
        idx = _stratified_sample(y, 10, seed=2)
        assert len(idx) == len(set(idx.tolist()))

    def test_contains_both_classes(self) -> None:
        y = self._labels(10, 10)
        idx = _stratified_sample(y, 6, seed=3)
        sampled_labels = y[idx]
        assert 0 in sampled_labels
        assert 1 in sampled_labels

    def test_reproducible_with_same_seed(self) -> None:
        y = self._labels(15, 15)
        idx1 = _stratified_sample(y, 8, seed=42)
        idx2 = _stratified_sample(y, 8, seed=42)
        np.testing.assert_array_equal(sorted(idx1), sorted(idx2))

    def test_different_seeds_give_different_results(self) -> None:
        y = self._labels(20, 20)
        idx1 = _stratified_sample(y, 10, seed=0)
        idx2 = _stratified_sample(y, 10, seed=99)
        # Not guaranteed to differ, but very likely with n=40, k=10
        assert not np.array_equal(sorted(idx1), sorted(idx2))

    def test_handles_imbalanced_classes(self) -> None:
        y = self._labels(2, 18)
        idx = _stratified_sample(y, 4, seed=5)
        assert len(idx) >= 2   # at minimum one of each class


# ── _expand_windows ────────────────────────────────────────────────────────────

class TestExpandWindows:
    def _make_clip_data(self, n_clips: int = 5, n_windows: int = 4) -> tuple:
        clip_X = [
            np.random.randn(n_windows, 30, 13).astype(np.float32)
            for _ in range(n_clips)
        ]
        clip_y = np.array([1, 0, 1, 0, 1], dtype=np.int32)[:n_clips]
        return clip_X, clip_y

    def test_output_shapes(self) -> None:
        clip_X, clip_y = self._make_clip_data(5, 4)
        X, y = _expand_windows(clip_X, clip_y, np.arange(5))
        assert X.shape == (20, 30, 13)   # 5 clips * 4 windows
        assert y.shape == (20,)

    def test_label_propagation(self) -> None:
        """All windows of an anomalous clip should have label 1."""
        clip_X = [np.zeros((3, 30, 13), dtype=np.float32)] * 2
        clip_y = np.array([1, 0], dtype=np.int32)
        X, y = _expand_windows(clip_X, clip_y, np.array([0, 1]))
        assert all(y[:3] == 1)   # first clip windows
        assert all(y[3:] == 0)   # second clip windows

    def test_subset_indices(self) -> None:
        clip_X, clip_y = self._make_clip_data(5, 4)
        X, y = _expand_windows(clip_X, clip_y, np.array([0, 2]))
        assert X.shape == (8, 30, 13)
        assert y.shape == (8,)

    def test_dtype_float32(self) -> None:
        clip_X, clip_y = self._make_clip_data(3, 2)
        X, y = _expand_windows(clip_X, clip_y, np.arange(3))
        assert X.dtype == np.float32
        assert y.dtype == np.float32


# ── _compute_metrics ───────────────────────────────────────────────────────────

class TestComputeMetrics:
    def test_perfect_predictions(self) -> None:
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        y_prob = np.array([0.1, 0.1, 0.9, 0.9])
        m = _compute_metrics(y_true, y_pred, y_prob)
        assert m["f1"] == pytest.approx(1.0)
        assert m["auc_roc"] == pytest.approx(1.0)
        assert m["precision"] == pytest.approx(1.0)
        assert m["recall"] == pytest.approx(1.0)

    def test_all_wrong(self) -> None:
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([1, 1, 0, 0])
        y_prob = np.array([0.9, 0.9, 0.1, 0.1])
        m = _compute_metrics(y_true, y_pred, y_prob)
        assert m["f1"] == pytest.approx(0.0)

    def test_returns_all_keys(self) -> None:
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        y_prob = np.array([0.1, 0.9, 0.2, 0.8])
        m = _compute_metrics(y_true, y_pred, y_prob)
        assert set(m.keys()) == {"f1", "auc_roc", "precision", "recall"}

    def test_all_values_in_range(self) -> None:
        rng = np.random.default_rng(0)
        y_true = rng.integers(0, 2, size=50)
        y_pred = rng.integers(0, 2, size=50)
        y_prob = rng.random(50)
        m = _compute_metrics(y_true, y_pred, y_prob)
        for v in m.values():
            assert 0.0 <= v <= 1.0

    def test_single_class_auc_fallback(self) -> None:
        """If only one class in y_true, AUC-ROC should return 0.5 (not raise)."""
        y_true = np.array([0, 0, 0, 0])
        y_pred = np.array([0, 0, 0, 0])
        y_prob = np.array([0.1, 0.2, 0.3, 0.1])
        m = _compute_metrics(y_true, y_pred, y_prob)
        assert m["auc_roc"] == pytest.approx(0.5)


# ── aggregate_results ──────────────────────────────────────────────────────────

class TestAggregateResults:
    def _make_results(self) -> dict:
        """Synthetic raw results: 3 repeats per fraction."""
        raw = {}
        for frac in TRAIN_FRACTIONS:
            raw[frac] = [
                {"f1": 0.6 + frac * 0.2 + 0.01 * r,
                 "auc_roc": 0.65 + frac * 0.15 + 0.01 * r,
                 "precision": 0.7,
                 "recall": 0.6}
                for r in range(3)
            ]
        return raw

    def test_all_fractions_present(self) -> None:
        agg = aggregate_results(self._make_results())
        assert set(agg.keys()) == set(TRAIN_FRACTIONS)

    def test_all_metrics_present(self) -> None:
        agg = aggregate_results(self._make_results())
        for frac in TRAIN_FRACTIONS:
            assert set(agg[frac].keys()) == {"f1", "auc_roc", "precision", "recall"}

    def test_mean_and_std_keys(self) -> None:
        agg = aggregate_results(self._make_results())
        for frac in TRAIN_FRACTIONS:
            for metric in ["f1", "auc_roc"]:
                assert "mean" in agg[frac][metric]
                assert "std" in agg[frac][metric]

    def test_mean_is_average(self) -> None:
        raw = {
            0.5: [
                {"f1": 0.6, "auc_roc": 0.7, "precision": 0.8, "recall": 0.5},
                {"f1": 0.8, "auc_roc": 0.9, "precision": 0.7, "recall": 0.7},
            ]
        }
        agg = aggregate_results(raw)
        assert agg[0.5]["f1"]["mean"] == pytest.approx(0.7)
        assert agg[0.5]["auc_roc"]["mean"] == pytest.approx(0.8)

    def test_std_zero_when_identical(self) -> None:
        raw = {
            1.0: [
                {"f1": 0.85, "auc_roc": 0.90, "precision": 0.80, "recall": 0.88},
                {"f1": 0.85, "auc_roc": 0.90, "precision": 0.80, "recall": 0.88},
            ]
        }
        agg = aggregate_results(raw)
        assert agg[1.0]["f1"]["std"] == pytest.approx(0.0)

    def test_higher_fraction_higher_mean_f1(self) -> None:
        """Aggregated means should increase with more training data."""
        agg = aggregate_results(self._make_results())
        means = [agg[f]["f1"]["mean"] for f in TRAIN_FRACTIONS]
        assert means == sorted(means), "Expected F1 to increase with more data"

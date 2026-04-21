"""
Unit tests for the classical ML feature extraction and classifier.

Tests use synthetic data — no video files, no DB connection, no R2 access.
"""

from pathlib import Path

import numpy as np
import pytest

from scripts.build_features import (
    _max_consecutive_true,
    _zero_features,
    feature_names,
    load_features,
    save_features,
)
from scripts.models.classical import ClassicalAnomalyClassifier, ClassicalResult


# ── Feature name contract ──────────────────────────────────────────────────────


class TestFeatureNames:
    """Verify the feature vector contract is stable."""

    def test_returns_list_of_strings(self) -> None:
        names = feature_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_expected_count(self) -> None:
        assert len(feature_names()) == 19

    def test_zero_features_matches_names(self) -> None:
        zeros = _zero_features()
        assert set(zeros.keys()) == set(feature_names())

    def test_all_values_zero(self) -> None:
        for v in _zero_features().values():
            assert v == 0.0

    def test_required_features_present(self) -> None:
        names = set(feature_names())
        required = {
            "flow_mean",
            "flow_max",
            "flow_p95",
            "window_n_flagged",
            "spike_rate",
            "max_consecutive_spikes",
            "direction_variance",
            "blur_mean",
            "edge_density_std",
        }
        assert required.issubset(names)


# ── Consecutive spike helper ───────────────────────────────────────────────────


class TestMaxConsecutiveTrue:
    def test_all_false(self) -> None:
        assert _max_consecutive_true(np.array([False, False, False])) == 0

    def test_all_true(self) -> None:
        assert _max_consecutive_true(np.array([True, True, True])) == 3

    def test_single_run(self) -> None:
        assert _max_consecutive_true(np.array([False, True, True, True, False])) == 3

    def test_multiple_runs(self) -> None:
        mask = np.array([True, True, False, True, False, True, True, True])
        assert _max_consecutive_true(mask) == 3

    def test_empty(self) -> None:
        assert _max_consecutive_true(np.array([], dtype=bool)) == 0


# ── Feature save / load round-trip ────────────────────────────────────────────


class TestSaveLoadFeatures:
    def test_round_trip(self, tmp_path: Path) -> None:
        """Saved features should load back with identical values."""
        features = {k: float(i) for i, k in enumerate(feature_names())}
        clip_id = "test-clip-001"
        out_path = save_features(clip_id, features, output_dir=tmp_path)
        assert out_path.exists()
        loaded = load_features(clip_id, features_dir=tmp_path)
        assert loaded is not None
        assert loaded.shape == (len(feature_names()),)
        expected = np.array([features[k] for k in feature_names()], dtype=np.float32)
        np.testing.assert_array_almost_equal(loaded, expected)

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = load_features("nonexistent-clip", features_dir=tmp_path)
        assert result is None

    def test_output_is_compressed_npz(self, tmp_path: Path) -> None:
        features = _zero_features()
        path = save_features("test-clip", features, output_dir=tmp_path)
        assert path.suffix == ".npz"


# ── ClassicalAnomalyClassifier ────────────────────────────────────────────────


class TestClassicalAnomalyClassifier:
    """Tests for the classifier using synthetic data (no DB or R2 needed)."""

    def _make_synthetic_dataset(
        self, tmp_path: Path, n_normal: int = 20, n_anomaly: int = 20
    ) -> tuple[list[str], list[int]]:
        """
        Create synthetic .npz feature files in tmp_path.

        Normal clips: low flow_mean (2.0), no spikes.
        Anomaly clips: high flow_mean (25.0), many spikes.

        Returns:
            (clip_ids, labels) lists.
        """
        clip_ids, labels = [], []
        names = feature_names()

        for i in range(n_normal):
            cid = f"normal-{i:03d}"
            feats = {k: 2.0 for k in names}
            feats["flow_mean"] = 2.0
            feats["flow_max"] = 4.0
            feats["spike_rate"] = 0.0
            feats["window_n_flagged"] = 0.0
            save_features(cid, feats, output_dir=tmp_path)
            clip_ids.append(cid)
            labels.append(0)

        for i in range(n_anomaly):
            cid = f"anomaly-{i:03d}"
            feats = {k: 2.0 for k in names}
            feats["flow_mean"] = 25.0
            feats["flow_max"] = 40.0
            feats["flow_p95"] = 38.0
            feats["spike_rate"] = 0.7
            feats["window_n_flagged"] = 5.0
            feats["max_consecutive_spikes"] = 10.0
            save_features(cid, feats, output_dir=tmp_path)
            clip_ids.append(cid)
            labels.append(1)

        return clip_ids, labels

    def test_predict_returns_correct_type(self, tmp_path: Path) -> None:
        """predict() on a synthetic feature file returns ClassicalResult."""
        import xgboost as xgb
        from sklearn.preprocessing import StandardScaler

        names = feature_names()
        feats = _zero_features()
        feats["flow_mean"] = 5.0
        save_features("test-clip", feats, output_dir=tmp_path)

        # Build a minimal trained classifier inline
        clf = ClassicalAnomalyClassifier(model_path=tmp_path / "model.pkl")
        X = np.zeros((10, len(names)), dtype=np.float32)
        y = np.array([0, 1] * 5, dtype=np.int32)
        clf._scaler = StandardScaler().fit(X)
        clf._model = xgb.XGBClassifier(
            n_estimators=5, use_label_encoder=False, eval_metric="logloss"
        ).fit(clf._scaler.transform(X), y)
        clf._feature_names = names

        result = clf.predict("test-clip", features_dir=tmp_path)
        assert isinstance(result, ClassicalResult)
        assert result.clip_id == "test-clip"
        assert 0.0 <= result.anomaly_probability <= 1.0
        assert isinstance(result.is_anomaly, bool)

    def test_predict_raises_on_missing_features(self, tmp_path: Path) -> None:
        """predict() should raise FileNotFoundError for unknown clip_id."""
        import xgboost as xgb
        from sklearn.preprocessing import StandardScaler

        names = feature_names()
        clf = ClassicalAnomalyClassifier()
        X = np.zeros((4, len(names)), dtype=np.float32)
        y = np.array([0, 1, 0, 1], dtype=np.int32)
        clf._scaler = StandardScaler().fit(X)
        clf._model = xgb.XGBClassifier(
            n_estimators=5, use_label_encoder=False, eval_metric="logloss"
        ).fit(clf._scaler.transform(X), y)
        clf._feature_names = names

        with pytest.raises(FileNotFoundError):
            clf.predict("clip-that-does-not-exist", features_dir=tmp_path)

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Saved model loads back and produces identical predictions."""
        import xgboost as xgb
        from sklearn.preprocessing import StandardScaler

        names = feature_names()
        feats = _zero_features()
        feats["flow_mean"] = 5.0
        save_features("test-clip", feats, output_dir=tmp_path)

        model_path = tmp_path / "test_model.pkl"
        clf = ClassicalAnomalyClassifier(model_path=model_path)
        X = np.zeros((10, len(names)), dtype=np.float32)
        y = np.array([0, 1] * 5, dtype=np.int32)
        clf._scaler = StandardScaler().fit(X)
        clf._model = xgb.XGBClassifier(
            n_estimators=5, use_label_encoder=False, eval_metric="logloss"
        ).fit(clf._scaler.transform(X), y)
        clf._feature_names = names
        clf.save()

        # Load fresh instance
        clf2 = ClassicalAnomalyClassifier(model_path=model_path)
        clf2.load()
        r1 = clf.predict("test-clip", features_dir=tmp_path)
        r2 = clf2.predict("test-clip", features_dir=tmp_path)
        assert r1.anomaly_probability == pytest.approx(r2.anomaly_probability)

    def test_load_raises_if_no_model_file(self, tmp_path: Path) -> None:
        clf = ClassicalAnomalyClassifier(model_path=tmp_path / "nonexistent.pkl")
        with pytest.raises(FileNotFoundError):
            clf.load()

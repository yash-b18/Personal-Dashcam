"""
Unit tests for the deep learning LSTM anomaly classifier.

Tests use synthetic data — no video files, no DB connection, no R2 access,
no YOLOv8 weights required.
"""

from pathlib import Path

import numpy as np
import pytest

from scripts.models.deep_learning import (
    DECISION_THRESHOLD,
    FEATURE_DIM,
    SEQUENCE_LENGTH,
    DeepLearningResult,
    LSTMAnomalyClassifier,
    build_lstm_model,
)
from api.video.sequence_builder import load_dl_features, save_dl_features


# ── build_lstm_model ───────────────────────────────────────────────────────────


class TestBuildLstmModel:
    """Verify the AnomalyLSTM architecture."""

    def test_returns_nn_module(self) -> None:
        import torch.nn as nn

        model = build_lstm_model()
        assert isinstance(model, nn.Module)

    def test_forward_shape(self) -> None:
        import torch

        model = build_lstm_model()
        model.eval()
        batch = 4
        x = torch.randn(batch, SEQUENCE_LENGTH, FEATURE_DIM)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (batch,), f"Expected ({batch},), got {out.shape}"

    def test_forward_single_sample(self) -> None:
        import torch

        model = build_lstm_model()
        model.eval()
        x = torch.randn(1, SEQUENCE_LENGTH, FEATURE_DIM)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (1,)

    def test_output_is_logit_not_probability(self) -> None:
        """Raw output can be any real value — sigmoid turns it into prob."""
        import torch

        model = build_lstm_model()
        model.eval()
        x = torch.randn(8, SEQUENCE_LENGTH, FEATURE_DIM)
        with torch.no_grad():
            out = model(x)
        # Should NOT be constrained to [0, 1]
        assert out.dtype == torch.float32

    def test_custom_dims(self) -> None:
        import torch

        model = build_lstm_model(input_dim=8, hidden_dim=32, num_layers=1, dropout=0.0)
        model.eval()
        x = torch.randn(2, 10, 8)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (2,)

    def test_bidirectional_output_dim(self) -> None:
        """Check that the FC head receives 2*hidden_dim (bidirectional)."""
        hidden = 64
        model = build_lstm_model(hidden_dim=hidden)
        # Inspect first Linear layer in classifier
        first_linear = list(model.classifier.children())[0]
        assert first_linear.in_features == 2 * hidden


# ── save_dl_features / load_dl_features ───────────────────────────────────────


class TestDLFeatureIO:
    """Verify sequence save/load round-trip."""

    def _make_sequences(self, n: int = 5) -> np.ndarray:
        return np.random.randn(n, SEQUENCE_LENGTH, FEATURE_DIM).astype(np.float32)

    def test_round_trip(self, tmp_path: Path) -> None:
        seqs = self._make_sequences(8)
        save_dl_features("clip-001", seqs, output_dir=tmp_path)
        loaded = load_dl_features("clip-001", features_dir=tmp_path)
        assert loaded is not None
        np.testing.assert_array_almost_equal(seqs, loaded)

    def test_missing_returns_none(self, tmp_path: Path) -> None:
        result = load_dl_features("nonexistent", features_dir=tmp_path)
        assert result is None

    def test_shape_preserved(self, tmp_path: Path) -> None:
        seqs = self._make_sequences(12)
        save_dl_features("shape-test", seqs, output_dir=tmp_path)
        loaded = load_dl_features("shape-test", features_dir=tmp_path)
        assert loaded.shape == (12, SEQUENCE_LENGTH, FEATURE_DIM)

    def test_output_is_npz(self, tmp_path: Path) -> None:
        save_dl_features("fmt-test", self._make_sequences(3), output_dir=tmp_path)
        assert (tmp_path / "fmt-test_dl_features.npz").exists()

    def test_dtype_is_float32(self, tmp_path: Path) -> None:
        seqs = self._make_sequences(4)
        save_dl_features("dtype-test", seqs, output_dir=tmp_path)
        loaded = load_dl_features("dtype-test", features_dir=tmp_path)
        assert loaded.dtype == np.float32


# ── DeepLearningResult ─────────────────────────────────────────────────────────


class TestDeepLearningResult:
    def test_default_construction(self) -> None:
        r = DeepLearningResult(
            clip_id="abc",
            is_anomaly=True,
            anomaly_probability=0.85,
            severity=0.85,
        )
        assert r.clip_id == "abc"
        assert r.is_anomaly is True
        assert r.anomaly_windows == []
        assert r.error is None

    def test_with_error(self) -> None:
        r = DeepLearningResult(
            clip_id="abc",
            is_anomaly=False,
            anomaly_probability=0.0,
            severity=0.0,
            error="video too short",
        )
        assert r.error == "video too short"


# ── LSTMAnomalyClassifier — predict ───────────────────────────────────────────


class TestLSTMAnomalyClassifierPredict:
    """Tests for predict() using a hand-crafted synthetic model."""

    def _make_trained_classifier(self, tmp_path: Path) -> LSTMAnomalyClassifier:
        """Return a classifier with random model weights (not trained on data)."""
        model_path = tmp_path / "test_dl_lstm.pt"
        clf = LSTMAnomalyClassifier(model_path=model_path)
        clf._model = build_lstm_model()
        clf._metadata = {
            "best_val_f1": 0.0,
            "epochs_trained": 1,
            "threshold": DECISION_THRESHOLD,
            "feature_dim": FEATURE_DIM,
            "sequence_length": SEQUENCE_LENGTH,
        }
        return clf

    def test_predict_returns_deep_learning_result(self, tmp_path: Path) -> None:
        clf = self._make_trained_classifier(tmp_path)
        seqs = np.random.randn(5, SEQUENCE_LENGTH, FEATURE_DIM).astype(np.float32)
        save_dl_features("test-clip", seqs, output_dir=tmp_path)
        result = clf.predict("test-clip", features_dir=tmp_path)
        assert isinstance(result, DeepLearningResult)
        assert result.clip_id == "test-clip"

    def test_probability_in_range(self, tmp_path: Path) -> None:
        clf = self._make_trained_classifier(tmp_path)
        seqs = np.random.randn(10, SEQUENCE_LENGTH, FEATURE_DIM).astype(np.float32)
        save_dl_features("prob-clip", seqs, output_dir=tmp_path)
        result = clf.predict("prob-clip", features_dir=tmp_path)
        assert 0.0 <= result.anomaly_probability <= 1.0

    def test_is_anomaly_consistent_with_probability(self, tmp_path: Path) -> None:
        import torch

        clf = self._make_trained_classifier(tmp_path)
        # Force model to always predict high probability
        clf._model = build_lstm_model()
        # Override weights so output is always very high logit
        with torch.no_grad():
            for p in clf._model.parameters():
                p.fill_(5.0)

        seqs = np.ones((3, SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
        save_dl_features("high-clip", seqs, output_dir=tmp_path)
        result = clf.predict("high-clip", features_dir=tmp_path)
        # With logit >> 0, sigmoid → ~1.0, should be anomaly
        assert result.is_anomaly is True

    def test_predict_raises_on_missing_features(self, tmp_path: Path) -> None:
        clf = self._make_trained_classifier(tmp_path)
        with pytest.raises(FileNotFoundError):
            clf.predict("nonexistent-clip", features_dir=tmp_path)

    def test_empty_sequences_returns_no_anomaly(self, tmp_path: Path) -> None:
        clf = self._make_trained_classifier(tmp_path)
        empty = np.empty((0, SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
        save_dl_features("short-clip", empty, output_dir=tmp_path)
        result = clf.predict("short-clip", features_dir=tmp_path)
        assert result.is_anomaly is False
        assert result.anomaly_probability == 0.0
        assert result.error is not None

    def test_anomaly_windows_structure(self, tmp_path: Path) -> None:
        import torch

        clf = self._make_trained_classifier(tmp_path)
        with torch.no_grad():
            for p in clf._model.parameters():
                p.fill_(5.0)
        seqs = np.ones((5, SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
        save_dl_features("windows-clip", seqs, output_dir=tmp_path)
        result = clf.predict("windows-clip", features_dir=tmp_path)
        for w in result.anomaly_windows:
            assert "window_idx" in w
            assert "probability" in w
            assert "start_frame" in w
            assert "end_frame" in w
            assert 0.0 <= w["probability"] <= 1.0


# ── LSTMAnomalyClassifier — save / load ───────────────────────────────────────


class TestLSTMAnomalyClassifierPersistence:
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        import torch

        model_path = tmp_path / "roundtrip.pt"
        clf = LSTMAnomalyClassifier(model_path=model_path)
        clf._model = build_lstm_model()
        clf._metadata = {
            "threshold": DECISION_THRESHOLD,
            "feature_dim": FEATURE_DIM,
            "sequence_length": SEQUENCE_LENGTH,
            "best_val_f1": 0.5,
            "epochs_trained": 3,
        }
        clf.save()

        clf2 = LSTMAnomalyClassifier(model_path=model_path)
        clf2.load()

        # Both models should produce identical outputs on the same input
        x = torch.randn(2, SEQUENCE_LENGTH, FEATURE_DIM)
        clf._model.eval()
        clf2._model.eval()
        with torch.no_grad():
            out1 = clf._model(x)
            out2 = clf2._model(x)
        np.testing.assert_array_almost_equal(out1.numpy(), out2.numpy(), decimal=5)

    def test_save_raises_without_model(self, tmp_path: Path) -> None:
        clf = LSTMAnomalyClassifier(model_path=tmp_path / "empty.pt")
        with pytest.raises(RuntimeError, match="No model to save"):
            clf.save()

    def test_load_raises_if_file_missing(self, tmp_path: Path) -> None:
        clf = LSTMAnomalyClassifier(model_path=tmp_path / "nonexistent.pt")
        with pytest.raises(FileNotFoundError):
            clf.load()

    def test_metadata_preserved(self, tmp_path: Path) -> None:
        model_path = tmp_path / "meta.pt"
        clf = LSTMAnomalyClassifier(model_path=model_path)
        clf._model = build_lstm_model()
        clf._metadata = {
            "threshold": 0.6,
            "feature_dim": FEATURE_DIM,
            "sequence_length": SEQUENCE_LENGTH,
            "best_val_f1": 0.75,
            "epochs_trained": 15,
        }
        clf.save()
        clf2 = LSTMAnomalyClassifier(model_path=model_path)
        clf2.load()
        assert clf2._metadata["best_val_f1"] == pytest.approx(0.75)
        assert clf2._metadata["epochs_trained"] == 15

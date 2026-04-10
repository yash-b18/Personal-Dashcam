"""
Deep learning anomaly detector — bidirectional LSTM on YOLOv8 feature sequences.

Architecture:
  Stage 1 — Per-frame feature extraction (api/video/sequence_builder.py):
    YOLOv8 object detections + optical flow → 13-dim feature vector per frame
    Sliding window (30 frames, 50% overlap) → shape (n_windows, 30, 13)

  Stage 2 — Temporal classification (AnomalyLSTM):
    Bidirectional LSTM (2 layers, hidden=128 → 256 bidirectional output)
    Mean temporal pooling → FC head (256 → 64 → 1)
    Output: anomaly probability per window

  Stage 3 — Clip-level aggregation:
    Clip is anomalous if any window probability > threshold (default 0.5)
    Clip severity = max window probability

Training:
  Loss:      BCEWithLogitsLoss with pos_weight for class imbalance
  Optimizer: AdamW (lr=1e-3, weight_decay=1e-4)
  Scheduler: CosineAnnealingLR
  Early stopping: patience=10 epochs on validation F1
  Data augmentation: Gaussian noise on features, random temporal jitter

Feature sequences are pre-extracted and cached (run build_dl_features.py first).
Model weights saved to models/dl_lstm.pt.
"""

import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SEQUENCE_LENGTH = 30
FEATURE_DIM = 13
HIDDEN_DIM = 128
NUM_LAYERS = 2
DROPOUT = 0.3
DECISION_THRESHOLD = 0.5

MODEL_PATH = Path("models/dl_lstm.pt")
EVAL_OUTPUT_PATH = Path("data/outputs/dl_eval.json")


# ── PyTorch model ──────────────────────────────────────────────────────────────

def build_lstm_model(
    input_dim: int = FEATURE_DIM,
    hidden_dim: int = HIDDEN_DIM,
    num_layers: int = NUM_LAYERS,
    dropout: float = DROPOUT,
):
    """
    Construct the bidirectional LSTM anomaly classifier.

    Args:
        input_dim: Feature vector size per frame (default 13).
        hidden_dim: LSTM hidden size per direction (output = 2 * hidden_dim).
        num_layers: Number of LSTM layers.
        dropout: Dropout probability between LSTM layers and in FC head.

    Returns:
        nn.Module — the AnomalyLSTM model.
    """
    import torch.nn as nn

    class AnomalyLSTM(nn.Module):
        """
        Bidirectional LSTM for temporal anomaly detection in dashcam footage.

        Input:  (batch, seq_len, input_dim)
        Output: (batch,) — raw logit per sequence window
        """

        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                bidirectional=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
            lstm_out_dim = 2 * hidden_dim   # bidirectional
            self.classifier = nn.Sequential(
                nn.Linear(lstm_out_dim, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, 1),
            )

        def forward(self, x):
            """
            Args:
                x: Tensor (batch, seq_len, input_dim)
            Returns:
                Tensor (batch,) — logits (apply sigmoid for probabilities)
            """
            lstm_out, _ = self.lstm(x)          # (batch, seq_len, 2*hidden_dim)
            pooled = lstm_out.mean(dim=1)        # (batch, 2*hidden_dim)
            return self.classifier(pooled).squeeze(-1)  # (batch,)

    return AnomalyLSTM()


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class DeepLearningResult:
    """Inference result from the LSTM classifier for a single clip."""
    clip_id: str
    is_anomaly: bool
    anomaly_probability: float      # max window probability
    severity: float                 # same as anomaly_probability
    anomaly_windows: list[dict] = field(default_factory=list)
    # Each: {"window_idx": int, "probability": float, "start_frame": int, "end_frame": int}
    error: str | None = None


# ── Classifier wrapper ─────────────────────────────────────────────────────────

class LSTMAnomalyClassifier:
    """
    Wrapper for training, inference, and persistence of the AnomalyLSTM model.

    Handles dataset loading, training loop with early stopping, evaluation
    metrics, and clean save/load of weights + metadata.
    """

    def __init__(
        self,
        model_path: str | Path = MODEL_PATH,
        device: str | None = None,
        threshold: float = DECISION_THRESHOLD,
    ) -> None:
        import torch
        self.model_path = Path(model_path)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.threshold = threshold
        self._model = None
        self._metadata: dict = {}

    # ── Training ──────────────────────────────────────────────────────────────

    def train(
        self,
        features_dir: str | Path = "data/processed",
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 1e-3,
        val_split: float = 0.2,
        patience: int = 10,
        random_state: int = 42,
    ) -> dict[str, list[float]]:
        """
        Train the LSTM on pre-extracted DL feature sequences.

        Loads sequences from {features_dir}/{clip_id}_dl_features.npz and
        labels from the DB. Applies per-window label (all windows of an
        anomalous clip are labelled positive). Trains with early stopping
        on validation F1 and saves the best checkpoint.

        Args:
            features_dir: Directory containing *_dl_features.npz files.
            epochs: Maximum training epochs.
            batch_size: Sequences per batch.
            learning_rate: Initial AdamW learning rate.
            val_split: Fraction of data held out for validation.
            patience: Early stopping patience (epochs without val F1 improvement).
            random_state: NumPy / PyTorch seed for reproducibility.

        Returns:
            Training history dict:
            {train_loss, val_loss, val_f1, val_auc} — one value per epoch.
        """
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import f1_score, roc_auc_score

        torch.manual_seed(random_state)
        np.random.seed(random_state)

        X, y = self._load_dataset(features_dir)
        if X is None:
            raise RuntimeError(
                "No labeled DL feature sequences found. "
                "Run: python scripts/model.py --extract-dl-features"
            )

        logger.info(
            "Training dataset: %d windows (%d anomaly, %d normal)",
            len(y), int(np.sum(y)), int(len(y) - np.sum(y)),
        )

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=val_split, stratify=y, random_state=random_state
        )

        def _to_tensors(X_arr, y_arr):
            Xt = torch.tensor(X_arr, dtype=torch.float32)
            yt = torch.tensor(y_arr, dtype=torch.float32)
            return TensorDataset(Xt, yt)

        train_loader = DataLoader(_to_tensors(X_train, y_train),
                                  batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(_to_tensors(X_val, y_val),
                                batch_size=batch_size, shuffle=False)

        model = build_lstm_model().to(self.device)
        pos_weight = torch.tensor(
            [(len(y_train) - y_train.sum()) / max(y_train.sum(), 1)],
            dtype=torch.float32,
        ).to(self.device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        history = {k: [] for k in ["train_loss", "val_loss", "val_f1", "val_auc"]}
        best_val_f1 = -1.0
        patience_counter = 0
        best_state = None

        for epoch in range(epochs):
            # ── Train ─────────────────────────────────────────────────────
            model.train()
            train_losses = []
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                # Augmentation: add small Gaussian noise
                X_batch = X_batch + torch.randn_like(X_batch) * 0.02
                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                train_losses.append(loss.item())
            scheduler.step()

            # ── Validate ──────────────────────────────────────────────────
            model.eval()
            val_losses, val_probs, val_true = [], [], []
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                    logits = model(X_batch)
                    val_losses.append(criterion(logits, y_batch).item())
                    val_probs.extend(torch.sigmoid(logits).cpu().numpy().tolist())
                    val_true.extend(y_batch.cpu().numpy().tolist())

            val_preds = [int(p >= self.threshold) for p in val_probs]
            val_f1 = f1_score(val_true, val_preds, zero_division=0)
            val_auc = roc_auc_score(val_true, val_probs) if len(set(val_true)) > 1 else 0.5

            history["train_loss"].append(float(np.mean(train_losses)))
            history["val_loss"].append(float(np.mean(val_losses)))
            history["val_f1"].append(val_f1)
            history["val_auc"].append(val_auc)

            logger.info(
                "Epoch %d/%d | train_loss=%.4f val_loss=%.4f val_f1=%.4f val_auc=%.4f",
                epoch + 1, epochs,
                history["train_loss"][-1], history["val_loss"][-1], val_f1, val_auc,
            )

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("Early stopping at epoch %d (patience=%d)", epoch + 1, patience)
                    break

        if best_state:
            model.load_state_dict(best_state)
        self._model = model
        self._metadata = {
            "best_val_f1": best_val_f1,
            "epochs_trained": epoch + 1,
            "threshold": self.threshold,
            "feature_dim": FEATURE_DIM,
            "sequence_length": SEQUENCE_LENGTH,
        }
        self.save()
        self._save_eval(history)
        return history

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(
        self,
        clip_id: str,
        features_dir: str | Path = "data/processed",
    ) -> DeepLearningResult:
        """
        Run inference on a single clip using pre-extracted DL features.

        A clip is flagged as anomalous if any window probability exceeds
        self.threshold. Severity is the maximum window probability.

        Args:
            clip_id: UUID string of the clip.
            features_dir: Directory containing *_dl_features.npz files.

        Returns:
            DeepLearningResult with anomaly flag, probability, and windows.
        """
        import torch
        from api.video.sequence_builder import load_dl_features

        if self._model is None:
            self.load()

        sequences = load_dl_features(clip_id, Path(features_dir))
        if sequences is None:
            raise FileNotFoundError(
                f"No DL features for clip {clip_id}. Run extract-dl-features first."
            )

        if len(sequences) == 0:
            return DeepLearningResult(
                clip_id=clip_id, is_anomaly=False, severity=0.0,
                anomaly_probability=0.0, error="video too short"
            )

        self._model.eval()
        with torch.no_grad():
            X = torch.tensor(sequences, dtype=torch.float32).to(self.device)
            logits = self._model(X)
            probs = torch.sigmoid(logits).cpu().numpy()

        anomaly_windows = []
        for i, prob in enumerate(probs):
            if float(prob) >= self.threshold:
                start_frame = i * SEQUENCE_LENGTH // 2   # approx (step = 50%)
                anomaly_windows.append({
                    "window_idx": i,
                    "probability": float(prob),
                    "start_frame": start_frame,
                    "end_frame": start_frame + SEQUENCE_LENGTH,
                })

        max_prob = float(np.max(probs))
        return DeepLearningResult(
            clip_id=clip_id,
            is_anomaly=max_prob >= self.threshold,
            anomaly_probability=max_prob,
            severity=max_prob,
            anomaly_windows=anomaly_windows,
        )

    def predict_from_video(
        self,
        video_path: str | Path,
        clip_id: str,
        yolo_model_path: str = "models/yolov8m.pt",
    ) -> DeepLearningResult:
        """
        End-to-end inference on a local video file (no pre-extracted features).

        Builds sequences on the fly using SequenceBuilder, then runs LSTM.
        Slower than predict() — use for single-clip demos.

        Args:
            video_path: Path to local MP4.
            clip_id: UUID string for the result.
            yolo_model_path: Path to YOLOv8 weights.

        Returns:
            DeepLearningResult.
        """
        from api.video.sequence_builder import SequenceBuilder

        builder = SequenceBuilder(yolo_model_path=yolo_model_path, device=self.device)
        sequences = builder.build_sequences(video_path)

        if len(sequences) == 0:
            return DeepLearningResult(
                clip_id=clip_id, is_anomaly=False, severity=0.0,
                anomaly_probability=0.0, error="video too short",
            )

        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".npz"))
        try:
            from api.video.sequence_builder import save_dl_features
            save_dl_features(clip_id, sequences, output_dir=tmp.parent)
            return self.predict(clip_id, features_dir=tmp.parent)
        finally:
            dl_path = tmp.parent / f"{clip_id}_dl_features.npz"
            if dl_path.exists():
                dl_path.unlink()

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Save model weights and metadata to models/dl_lstm.pt."""
        import torch
        if self._model is None:
            raise RuntimeError("No model to save — train first.")
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"state_dict": self._model.state_dict(),
                    "metadata": self._metadata}, str(self.model_path))
        logger.info("Saved LSTM model to %s", self.model_path)

    def load(self) -> None:
        """Load model weights from models/dl_lstm.pt."""
        import torch
        if not self.model_path.exists():
            raise FileNotFoundError(f"No model at {self.model_path}. Train first.")
        checkpoint = torch.load(str(self.model_path), map_location=self.device)
        self._metadata = checkpoint.get("metadata", {})
        self._model = build_lstm_model().to(self.device)
        self._model.load_state_dict(checkpoint["state_dict"])
        self._model.eval()
        logger.info("Loaded LSTM model from %s", self.model_path)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_dataset(
        self, features_dir: str | Path
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """
        Build training arrays from .npz feature files and DB labels.

        Each clip contributes n_windows rows. All windows of an anomalous
        clip receive label 1; all windows of a normal clip receive label 0.

        Returns:
            (X array shape (n_windows, SEQ_LEN, FEAT_DIM),
             y array shape (n_windows,)) or (None, None) if no data.
        """
        from api.database import SessionLocal
        from api.models.db_models import Clip, Label
        from api.video.sequence_builder import load_dl_features

        features_dir = Path(features_dir)
        db = SessionLocal()
        all_X, all_y = [], []

        try:
            labeled = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
            if not labeled:
                return None, None

            for clip, label in labeled:
                seqs = load_dl_features(str(clip.id), features_dir)
                if seqs is None or len(seqs) == 0:
                    logger.warning("No DL features for %s — skipping", clip.filename_prefix)
                    continue
                all_X.append(seqs)
                all_y.extend([int(label.is_anomaly)] * len(seqs))
        finally:
            db.close()

        if not all_X:
            return None, None

        return np.concatenate(all_X, axis=0), np.array(all_y, dtype=np.float32)

    def _save_eval(self, history: dict) -> None:
        """Save training history to JSON for analysis."""
        EVAL_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = {"history": history, "metadata": self._metadata}
        EVAL_OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        logger.info("Saved DL eval to %s", EVAL_OUTPUT_PATH)

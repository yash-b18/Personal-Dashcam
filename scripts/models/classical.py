"""
Classical ML anomaly classifier — XGBoost on extracted clip features.

Pipeline:
  1. Load pre-extracted features from data/processed/ (built by build_features.py)
  2. Feature vector per clip:
       - Optical flow stats: [mean, std, max, skewness, kurtosis] per 1-sec window
       - YOLO detection counts: vehicles, pedestrians, signs, lights
       - Proximity score: max(bbox_area / frame_area) for nearest detected object
       - Motion direction variance
       - Edge density delta (Canny edge count changes)
  3. Train XGBoost binary classifier on human-labeled clips
  4. Evaluate with stratified k-fold, report F1 / AUC-ROC / precision / recall
  5. Save trained model to models/classical_xgb.pkl

Implemented in: feature/classical-ml
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ClassicalResult:
    """Inference result from the classical ML classifier."""
    clip_id: str
    is_anomaly: bool
    anomaly_probability: float          # 0.0 – 1.0
    feature_importances: dict[str, float] = field(default_factory=dict)
    top_anomaly_type: str | None = None


class ClassicalAnomalyClassifier:
    """
    XGBoost-based anomaly classifier trained on human-labeled clips.

    Implemented in feature/classical-ml.
    """

    MODEL_PATH = Path("models/classical_xgb.pkl")

    def __init__(self, model_path: str | Path | None = None) -> None:
        self.model_path = Path(model_path) if model_path else self.MODEL_PATH
        self._model: Any = None  # loaded XGBoost model

    def train(
        self,
        features_dir: str | Path = "data/processed",
        labels_path: str | Path = "data/outputs/labels.csv",
        n_folds: int = 5,
    ) -> dict[str, float]:
        """
        Train the XGBoost classifier on labeled clip features.

        Args:
            features_dir: Directory containing per-clip .npz feature files.
            labels_path: CSV with clip_id, is_anomaly columns.
            n_folds: Number of stratified k-fold splits for evaluation.

        Returns:
            Dict of evaluation metrics: {f1, auc_roc, precision, recall}.
        """
        raise NotImplementedError("Implemented in feature/classical-ml")

    def predict(self, clip_id: str, features_dir: str | Path = "data/processed") -> ClassicalResult:
        """
        Run inference on a single clip using pre-extracted features.

        Args:
            clip_id: UUID string of the clip to predict.
            features_dir: Directory containing .npz feature files.

        Returns:
            ClassicalResult with anomaly probability and feature importances.
        """
        raise NotImplementedError("Implemented in feature/classical-ml")

    def load(self) -> None:
        """Load trained model weights from disk."""
        raise NotImplementedError("Implemented in feature/classical-ml")

    def save(self) -> None:
        """Persist trained model weights to disk."""
        raise NotImplementedError("Implemented in feature/classical-ml")

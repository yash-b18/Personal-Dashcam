"""
Model training and inference orchestration script.

Supports training and running inference for all three model tiers:
  - baseline    : Optical flow thresholding (no training needed)
  - classical   : XGBoost classifier on extracted features
  - deep_learning: YOLOv8 + LSTM temporal classifier

Saves trained weights to models/ directory.
Writes inference results to data/outputs/.

Implemented in: feature/naive-baseline, feature/classical-ml, feature/deep-learning

Usage:
    python scripts/model.py --train --model classical
    python scripts/model.py --predict --model deep_learning --clip-id UUID
    python scripts/model.py --predict --model all
"""

import argparse


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Train or run inference for DashcamIQ models")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train", action="store_true", help="Train the specified model")
    mode.add_argument("--predict", action="store_true", help="Run inference")
    parser.add_argument(
        "--model",
        choices=["baseline", "classical", "deep_learning", "all"],
        default="all",
        help="Which model to use",
    )
    parser.add_argument("--clip-id", type=str, default=None, help="Run inference on a single clip")
    return parser.parse_args()


def main() -> None:
    """Train or predict. Implemented in respective feature branches."""
    args = parse_args()
    raise NotImplementedError(
        f"Model={args.model} train={args.train} predict={args.predict}. "
        "Implemented in feature/naive-baseline, feature/classical-ml, feature/deep-learning."
    )


if __name__ == "__main__":
    main()

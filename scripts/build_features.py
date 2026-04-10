"""
Feature extraction pipeline — runs after make_dataset.py.

For each processed clip, extracts:
  - Dense optical flow statistics (mean, std, max magnitude per frame)
  - YOLOv8 per-frame object detections
  - Motion direction variance
  - Edge density changes

Saves feature arrays to data/processed/ as numpy .npz files, one per clip.

Implemented in: feature/classical-ml

Usage:
    python scripts/build_features.py [--clip-id UUID] [--all]
"""

import argparse


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Extract features from dashcam clips")
    parser.add_argument("--clip-id", type=str, default=None, help="Process a single clip by UUID")
    parser.add_argument("--all", action="store_true", help="Process all clips without features")
    return parser.parse_args()


def main() -> None:
    """Run feature extraction. Implemented in feature/classical-ml."""
    args = parse_args()
    raise NotImplementedError(
        "Implemented in feature/classical-ml. "
        f"Args: clip_id={args.clip_id}, all={args.all}"
    )


if __name__ == "__main__":
    main()

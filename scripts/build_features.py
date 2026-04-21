"""
Feature extraction pipeline — runs after make_dataset.py, before classical ML training.

For each clip, downloads the front-view video from R2, extracts a fixed-size
feature vector, and saves it as data/processed/{clip_id}_features.npz.

Feature vector (~19 interpretable features per clip):

  Optical flow magnitude:
    flow_mean, flow_std, flow_max, flow_p75, flow_p90, flow_p95

  Window-level (30-frame sliding windows):
    window_max_mean, window_max_peak, window_max_std, window_n_flagged

  Motion direction:
    direction_variance, direction_change_rate

  Motion blur (Laplacian variance):
    blur_mean, blur_min

  Edge density (Canny):
    edge_density_std, edge_density_max_change

  Temporal spike patterns:
    n_magnitude_spikes, spike_rate, max_consecutive_spikes

Usage:
    python scripts/build_features.py --all
    python scripts/build_features.py --clip-id <UUID>
    python scripts/build_features.py --all --force
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.models.baseline import (  # noqa: E402
    MAGNITUDE_THRESHOLD,
    STEP_SIZE_FRAMES,
    WINDOW_SIZE_FRAMES,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path("data/processed")
_FB_PARAMS = dict(
    pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0
)


def feature_names() -> list[str]:
    """Return the ordered list of feature names produced by extract_features()."""
    return [
        "flow_mean",
        "flow_std",
        "flow_max",
        "flow_p75",
        "flow_p90",
        "flow_p95",
        "window_max_mean",
        "window_max_peak",
        "window_max_std",
        "window_n_flagged",
        "direction_variance",
        "direction_change_rate",
        "blur_mean",
        "blur_min",
        "edge_density_std",
        "edge_density_max_change",
        "n_magnitude_spikes",
        "spike_rate",
        "max_consecutive_spikes",
    ]


def _zero_features() -> dict[str, float]:
    """Return a zero-valued feature dict (used on extraction failure)."""
    return {k: 0.0 for k in feature_names()}


def _max_consecutive_true(mask: np.ndarray) -> int:
    """Return the length of the longest run of True values in a boolean array."""
    if not np.any(mask):
        return 0
    max_run = current_run = 0
    for val in mask:
        if val:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


def extract_features(video_path: str | Path) -> dict[str, float]:
    """
    Extract a fixed-size feature vector from a single video file.

    All frames are downscaled to 640px wide before processing to match
    the baseline's resolution and ensure consistent feature magnitudes.

    Args:
        video_path: Path to a local MP4 file.

    Returns:
        Dict mapping feature name → float value.

    Raises:
        RuntimeError: If OpenCV cannot open the video.
    """
    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    magnitudes: list[float] = []
    directions: list[float] = []
    blur_scores: list[float] = []
    edge_counts: list[float] = []
    prev_gray: np.ndarray | None = None
    prev_direction: float | None = None
    direction_changes = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            if w > 640:
                frame = cv2.resize(
                    frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA
                )

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur_scores.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            edges = cv2.Canny(gray, threshold1=50, threshold2=150)
            edge_counts.append(float(np.sum(edges > 0)))

            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, **_FB_PARAMS)
                fx, fy = flow[..., 0], flow[..., 1]
                magnitudes.append(float(np.mean(np.sqrt(fx**2 + fy**2))))
                angle = float(np.mean(np.arctan2(fy, fx)))
                directions.append(angle)
                if prev_direction is not None:
                    delta = abs(angle - prev_direction)
                    delta = min(delta, 2 * np.pi - delta)
                    if delta > np.pi / 4:
                        direction_changes += 1
                prev_direction = angle

            prev_gray = gray
    finally:
        cap.release()

    if not magnitudes:
        logger.warning("No frames extracted from %s", video_path)
        return _zero_features()

    mags = np.array(magnitudes, dtype=np.float32)
    n = len(mags)

    # Optical flow magnitude stats
    flow_feats = {
        "flow_mean": float(np.mean(mags)),
        "flow_std": float(np.std(mags)),
        "flow_max": float(np.max(mags)),
        "flow_p75": float(np.percentile(mags, 75)),
        "flow_p90": float(np.percentile(mags, 90)),
        "flow_p95": float(np.percentile(mags, 95)),
    }

    # Window-level stats
    w_means, w_peaks, w_stds, n_flagged = [], [], [], 0
    for s in range(0, n - WINDOW_SIZE_FRAMES + 1, STEP_SIZE_FRAMES):
        wnd = mags[s : s + WINDOW_SIZE_FRAMES]
        peak = float(np.max(wnd))
        w_means.append(float(np.mean(wnd)))
        w_peaks.append(peak)
        w_stds.append(float(np.std(wnd)))
        if peak > MAGNITUDE_THRESHOLD:
            n_flagged += 1

    window_feats = {
        "window_max_mean": max(w_means, default=0.0),
        "window_max_peak": max(w_peaks, default=0.0),
        "window_max_std": max(w_stds, default=0.0),
        "window_n_flagged": float(n_flagged),
    }

    # Direction stats
    dirs = np.array(directions, dtype=np.float32)
    dir_feats = {
        "direction_variance": float(np.var(dirs)) if len(dirs) > 1 else 0.0,
        "direction_change_rate": direction_changes / max(n, 1),
    }

    # Motion blur
    blurs = np.array(blur_scores, dtype=np.float32)
    blur_feats = {"blur_mean": float(np.mean(blurs)), "blur_min": float(np.min(blurs))}

    # Edge density
    ea = np.array(edge_counts, dtype=np.float32)
    diffs = np.abs(np.diff(ea)) if len(ea) > 1 else np.array([0.0])
    edge_feats = {
        "edge_density_std": float(np.std(ea)),
        "edge_density_max_change": float(np.max(diffs)),
    }

    # Spike patterns
    spike_mask = mags > MAGNITUDE_THRESHOLD
    n_spikes = int(np.sum(spike_mask))
    spike_feats = {
        "n_magnitude_spikes": float(n_spikes),
        "spike_rate": n_spikes / max(n, 1),
        "max_consecutive_spikes": float(_max_consecutive_true(spike_mask)),
    }

    return {
        **flow_feats,
        **window_feats,
        **dir_feats,
        **blur_feats,
        **edge_feats,
        **spike_feats,
    }


def save_features(
    clip_id: str, features: dict[str, float], output_dir: Path = PROCESSED_DIR
) -> Path:
    """
    Persist extracted features to a compressed .npz archive.

    Args:
        clip_id: UUID string used as filename.
        features: Output of extract_features().
        output_dir: Destination directory.

    Returns:
        Path to the written .npz file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    names = feature_names()
    vector = np.array([features[k] for k in names], dtype=np.float32)
    out_path = output_dir / f"{clip_id}_features.npz"
    np.savez_compressed(str(out_path), features=vector, names=np.array(names))
    return out_path


def load_features(
    clip_id: str, features_dir: Path = PROCESSED_DIR
) -> np.ndarray | None:
    """
    Load a pre-extracted feature vector from disk.

    Args:
        clip_id: UUID string of the clip.
        features_dir: Directory containing .npz files.

    Returns:
        1-D float32 array of shape (n_features,), or None if not found.
    """
    path = features_dir / f"{clip_id}_features.npz"
    if not path.exists():
        return None
    return np.load(str(path))["features"]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Extract features from dashcam clips")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--clip-id", type=str, help="Extract for a single clip UUID")
    target.add_argument("--all", action="store_true", help="Extract for all clips")
    parser.add_argument(
        "--force", action="store_true", help="Re-extract even if .npz exists"
    )
    return parser.parse_args()


def main() -> None:
    """Run feature extraction for one or all clips."""
    args = parse_args()

    from api.config import get_settings
    from api.database import SessionLocal
    from api.models.db_models import Clip, ProcessingStatus
    from api.storage.r2_client import R2Client

    r2 = R2Client(get_settings())
    db = SessionLocal()
    try:
        if args.clip_id:
            clips = db.query(Clip).filter(Clip.id == args.clip_id).all()
        else:
            clips = (
                db.query(Clip)
                .filter(Clip.processing_status != ProcessingStatus.FAILED)
                .all()
            )
    finally:
        db.close()

    if not clips:
        logger.warning("No clips found.")
        sys.exit(0)

    skipped = extracted = failed = 0
    for clip in tqdm(clips, desc="Extracting features", unit="clip"):
        out_path = PROCESSED_DIR / f"{clip.id}_features.npz"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        tmp_path = None
        try:
            tmp_path = r2.download_to_temp(clip.r2_key_front)
            features = extract_features(tmp_path)
            save_features(str(clip.id), features)
            extracted += 1
        except Exception as exc:
            logger.error("Failed on %s: %s", clip.filename_prefix, exc)
            failed += 1
        finally:
            if tmp_path and Path(tmp_path).exists():
                Path(tmp_path).unlink()

    print("\n── Feature Extraction ─────────────────")
    print(f"  Extracted: {extracted}")
    print(f"  Skipped:   {skipped}  (already exist)")
    print(f"  Failed:    {failed}")
    print(f"  Output:    {PROCESSED_DIR}/")


if __name__ == "__main__":
    main()

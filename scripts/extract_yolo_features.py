"""
Per-clip YOLOv8 scene-feature extraction.

Adds scene-semantic features that the 19-dim motion vector (build_features.py)
can't see — exactly the gap that made type classification on motion alone
unreliable (e.g. traffic_violation has no motion signature).

For each video clip, runs YOLOv8m at 5 fps, and for every sampled frame
records per-class object counts and bbox areas. Those per-frame detections
are aggregated into a fixed 20-dim per-clip feature vector that slots cleanly
alongside the 19 motion features.

Feature vector (20 dims, all float32):
  For each of {car, truck, bus, motorcycle, bicycle, person,
               traffic_light, stop_sign} (8 classes):
      mean_count_per_frame   # 8 features
      max_count_per_frame    # 8 features
  plus 4 scene summaries:
      max_bbox_area_ratio           # nearest-vehicle proxy (largest bbox / frame area)
      traffic_light_presence_frac   # fraction of frames with a traffic light
      stop_sign_presence_frac       # fraction of frames with a stop sign
      pedestrian_presence_frac      # fraction of frames with a pedestrian

Output: data/processed/{clip_id}_yolo.npz  (key='yolo_features')

This script is designed to run identically on:
  - Local (CPU / MPS): `python scripts/extract_yolo_features.py --all`
  - Google Colab (GPU): see notebooks/yolo_extract_colab.ipynb

Usage:
    python scripts/extract_yolo_features.py --all
    python scripts/extract_yolo_features.py --clip-id <UUID>
    python scripts/extract_yolo_features.py --all --force
    python scripts/extract_yolo_features.py --input-dir <dir with .mp4>   # Colab mode
"""

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path("data/processed")
WEIGHTS_PATH = Path("models/yolov8m.pt")

# COCO class ids → our feature channel index. Order is locked — keep in sync
# with yolo_feature_names().
_CLASS_INDEX = {
    2:  0,   # car
    7:  1,   # truck
    5:  2,   # bus
    3:  3,   # motorcycle
    1:  4,   # bicycle
    0:  5,   # person
    9:  6,   # traffic light
    11: 7,   # stop sign
}
_N_CLASSES = len(_CLASS_INDEX)

SAMPLE_FPS = 5.0
CONF_THRESHOLD = 0.35


def yolo_feature_names() -> list[str]:
    """Ordered names for the 20 YOLO-derived features."""
    classes = ["car", "truck", "bus", "motorcycle", "bicycle",
               "person", "traffic_light", "stop_sign"]
    names = [f"yolo_{c}_mean" for c in classes]
    names += [f"yolo_{c}_max" for c in classes]
    names += [
        "yolo_max_bbox_area_ratio",
        "yolo_traffic_light_present_frac",
        "yolo_stop_sign_present_frac",
        "yolo_pedestrian_present_frac",
    ]
    return names


def _zero_vector() -> np.ndarray:
    return np.zeros(len(yolo_feature_names()), dtype=np.float32)


def _sample_frames(video_path: Path, target_fps: float) -> list[np.ndarray]:
    """Decode frames at `target_fps` (stride-sampled) to keep YOLO inference cheap."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video_path}")
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        stride = max(1, int(round(src_fps / target_fps)))
        frames, idx = [], 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                frames.append(frame)
            idx += 1
        return frames
    finally:
        cap.release()


def _aggregate(detections: list[dict], frame_area: float) -> np.ndarray:
    """Collapse per-frame detections into a single 20-dim feature vector."""
    vec = _zero_vector()
    if not detections:
        return vec

    n_frames = len(detections)
    counts = np.zeros((n_frames, _N_CLASSES), dtype=np.float32)
    max_area_per_frame = np.zeros(n_frames, dtype=np.float32)

    for i, dets in enumerate(detections):
        for cls_id, bbox_area in dets:
            ch = _CLASS_INDEX.get(int(cls_id))
            if ch is None:
                continue
            counts[i, ch] += 1.0
            if bbox_area > max_area_per_frame[i]:
                max_area_per_frame[i] = bbox_area

    vec[0:_N_CLASSES] = counts.mean(axis=0)
    vec[_N_CLASSES:2 * _N_CLASSES] = counts.max(axis=0)

    # Scene summaries (indices after the count block)
    max_bbox_ratio = float(max_area_per_frame.max() / max(frame_area, 1.0))
    vec[2 * _N_CLASSES + 0] = max_bbox_ratio
    vec[2 * _N_CLASSES + 1] = float((counts[:, _CLASS_INDEX[9]] > 0).mean())   # traffic_light
    vec[2 * _N_CLASSES + 2] = float((counts[:, _CLASS_INDEX[11]] > 0).mean())  # stop_sign
    vec[2 * _N_CLASSES + 3] = float((counts[:, _CLASS_INDEX[0]] > 0).mean())   # person

    return vec


def extract_yolo_features(
    video_path: str | Path,
    model,
    target_fps: float = SAMPLE_FPS,
    conf: float = CONF_THRESHOLD,
    imgsz: int = 640,
) -> np.ndarray:
    """Run YOLOv8 on one clip and return a 20-dim feature vector."""
    video_path = Path(video_path)
    frames = _sample_frames(video_path, target_fps)
    if not frames:
        return _zero_vector()

    frame_area = float(frames[0].shape[0] * frames[0].shape[1])

    # YOLO inference — batched for GPU efficiency.
    results = model.predict(
        frames,
        imgsz=imgsz,
        conf=conf,
        verbose=False,
    )

    per_frame = []
    for r in results:
        if r.boxes is None or len(r.boxes) == 0:
            per_frame.append([])
            continue
        cls = r.boxes.cls.cpu().numpy().astype(int)
        xyxy = r.boxes.xyxy.cpu().numpy()
        widths = xyxy[:, 2] - xyxy[:, 0]
        heights = xyxy[:, 3] - xyxy[:, 1]
        areas = widths * heights
        per_frame.append(list(zip(cls, areas)))

    return _aggregate(per_frame, frame_area).astype(np.float32)


def save_yolo_features(clip_id: str, vec: np.ndarray, out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{clip_id}_yolo.npz"
    np.savez_compressed(path, yolo_features=vec, feature_names=np.array(yolo_feature_names()))
    return path


def load_yolo_features(clip_id: str, processed_dir: Path = PROCESSED_DIR) -> np.ndarray | None:
    path = processed_dir / f"{clip_id}_yolo.npz"
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as data:
        return data["yolo_features"].astype(np.float32)


# ── CLI ────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--all", action="store_true", help="Process all labeled clips from DB.")
    src.add_argument("--clip-id", type=str, help="Single clip UUID from DB.")
    src.add_argument("--input-dir", type=Path,
                     help="Colab/offline mode: process every .mp4 in this dir. "
                          "Output is keyed by the filename stem.")
    p.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    p.add_argument("--weights", type=Path, default=WEIGHTS_PATH)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--device", type=str, default=None,
                   help="'cuda', 'mps', 'cpu'. If omitted, ultralytics auto-selects.")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def _load_model(weights: Path, device: str | None):
    from ultralytics import YOLO
    logger.info("Loading YOLOv8 weights from %s (device=%s)", weights, device or "auto")
    model = YOLO(str(weights))
    if device:
        model.to(device)
    return model


def _run_from_db(args: argparse.Namespace, model) -> None:
    from api.config import get_settings
    from api.database import SessionLocal
    from api.models.db_models import Clip, Label
    from api.storage.r2_client import R2Client

    r2 = R2Client(get_settings())
    db = SessionLocal()
    try:
        q = db.query(Clip).join(Label, Clip.id == Label.clip_id)
        if args.clip_id:
            q = q.filter(Clip.id == args.clip_id)
        clips = q.all()
    finally:
        db.close()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    extracted = skipped = failed = 0

    for clip in tqdm(clips, desc="YOLO features", unit="clip"):
        out = args.output_dir / f"{clip.id}_yolo.npz"
        if out.exists() and not args.force:
            skipped += 1
            continue
        tmp = None
        try:
            tmp = r2.download_to_temp(clip.r2_key_front)
            vec = extract_yolo_features(tmp, model, imgsz=args.imgsz)
            save_yolo_features(str(clip.id), vec, out_dir=args.output_dir)
            extracted += 1
        except Exception as exc:
            logger.error("Failed on %s: %s", clip.filename_prefix, exc)
            failed += 1
        finally:
            if tmp and Path(tmp).exists():
                Path(tmp).unlink()

    logger.info("── YOLO Feature Extraction ─────────────────")
    logger.info("  Extracted: %d", extracted)
    logger.info("  Skipped:   %d", skipped)
    logger.info("  Failed:    %d", failed)
    logger.info("  Output:    %s/", args.output_dir)


def _run_from_dir(args: argparse.Namespace, model) -> None:
    """Process a local directory of .mp4 files — used for Colab/offline runs."""
    videos = sorted(args.input_dir.glob("*.mp4"))
    if not videos:
        logger.error("No .mp4 files found in %s", args.input_dir)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    extracted = skipped = failed = 0

    for v in tqdm(videos, desc="YOLO features", unit="clip"):
        stem = v.stem   # expected to be the clip UUID when files are named <clip_id>.mp4
        out = args.output_dir / f"{stem}_yolo.npz"
        if out.exists() and not args.force:
            skipped += 1
            continue
        try:
            vec = extract_yolo_features(v, model, imgsz=args.imgsz)
            save_yolo_features(stem, vec, out_dir=args.output_dir)
            extracted += 1
        except Exception as exc:
            logger.error("Failed on %s: %s", v.name, exc)
            failed += 1

    logger.info("── YOLO Feature Extraction (offline) ───────")
    logger.info("  Extracted: %d", extracted)
    logger.info("  Skipped:   %d", skipped)
    logger.info("  Failed:    %d", failed)
    logger.info("  Output:    %s/", args.output_dir)


def main() -> None:
    args = parse_args()
    if not any([args.all, args.clip_id, args.input_dir]):
        logger.error("Specify --all, --clip-id <UUID>, or --input-dir <path>")
        sys.exit(1)

    model = _load_model(args.weights, args.device)

    if args.input_dir:
        _run_from_dir(args, model)
    else:
        _run_from_db(args, model)


if __name__ == "__main__":
    main()

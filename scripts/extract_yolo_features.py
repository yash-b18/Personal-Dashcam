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
    python scripts/extract_yolo_features.py --input-dir <dir with .mp4>       # offline mode
    python scripts/extract_yolo_features.py --manifest data/clip_manifest.json  # Colab mode
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Semaphore

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

SAMPLE_FPS = 2.0
CONF_THRESHOLD = 0.35
DEFAULT_IMGSZ = 480  # smaller than 640; accuracy diff on vehicle classes is <1%


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


def _sample_frames_decord(video_path: Path, target_fps: float) -> list[np.ndarray]:
    """Strided frame sampler using decord. Seeks through the file instead of
    decoding every frame like cv2 does — ~10x faster for small target_fps."""
    import decord
    # decord uses RGB by default; ultralytics expects BGR (cv2-style). Keep
    # returning BGR for parity with the cv2 fallback and YOLO preprocessing.
    vr = decord.VideoReader(str(video_path), ctx=decord.cpu(0))
    src_fps = float(vr.get_avg_fps() or 30.0)
    stride = max(1, int(round(src_fps / target_fps)))
    indices = list(range(0, len(vr), stride))
    if not indices:
        return []
    batch = vr.get_batch(indices).asnumpy()  # (N, H, W, 3) RGB
    return [frame[:, :, ::-1].copy() for frame in batch]  # RGB -> BGR


def _sample_frames_cv2(video_path: Path, target_fps: float) -> list[np.ndarray]:
    """Fallback sampler — cv2 read-every-frame-and-skip. Slow on long clips
    because it decodes every frame even when the stride is large."""
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


def _sample_frames(video_path: Path, target_fps: float) -> list[np.ndarray]:
    """Decode frames at `target_fps`. Prefer decord (seeks) over cv2 (reads all)."""
    try:
        import decord  # noqa: F401
        return _sample_frames_decord(video_path, target_fps)
    except ImportError:
        return _sample_frames_cv2(video_path, target_fps)


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
    imgsz: int = DEFAULT_IMGSZ,
    device: str | None = None,
    timings: dict | None = None,
) -> np.ndarray:
    """Run YOLOv8 on one clip and return a 20-dim feature vector."""
    video_path = Path(video_path)
    t0 = time.perf_counter()
    frames = _sample_frames(video_path, target_fps)
    decode_s = time.perf_counter() - t0
    if not frames:
        if timings is not None:
            timings.update(decode_s=decode_s, predict_s=0.0, n_frames=0)
        return _zero_vector()

    frame_area = float(frames[0].shape[0] * frames[0].shape[1])

    use_half = bool(device and device.startswith("cuda"))
    t1 = time.perf_counter()
    results = model.predict(
        frames,
        imgsz=imgsz,
        conf=conf,
        device=device,
        half=use_half,
        verbose=False,
    )
    predict_s = time.perf_counter() - t1
    if timings is not None:
        timings.update(decode_s=decode_s, predict_s=predict_s, n_frames=len(frames))

    per_frame: list = []
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


def _warmup_model(model, imgsz: int, device: str | None) -> None:
    """First predict() call is always slow — compiles kernels, allocates
    buffers, autotunes cudnn. Burn that cost up front on a dummy frame so
    the real clips don't pay it."""
    if not device or not device.startswith("cuda"):
        return
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    _ = model.predict([dummy], imgsz=imgsz, device=device, half=True, verbose=False)
    logger.info("  warmup predict: %.2fs", time.perf_counter() - t0)


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
                     help="Offline mode: process every .mp4 in this dir. "
                          "Output is keyed by the filename stem.")
    src.add_argument("--manifest", type=Path,
                     help="Colab mode: read a JSON list of {clip_id, r2_key_front} "
                          "and pull each clip from R2 using env-var credentials. "
                          "No DB access required.")
    p.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    p.add_argument("--weights", type=Path, default=WEIGHTS_PATH)
    p.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    p.add_argument("--device", type=str, default=None,
                   help="'cuda', 'mps', 'cpu'. If omitted, ultralytics auto-selects.")
    p.add_argument("--force", action="store_true")
    p.add_argument("--download-workers", type=int, default=8,
                   help="Parallel R2 download threads in --manifest mode (default 8).")
    p.add_argument("--prefetch", type=int, default=16,
                   help="Max clips buffered on disk ahead of GPU (default 16).")
    return p.parse_args()


def _load_model(weights: Path, device: str | None):
    import torch
    from ultralytics import YOLO
    logger.info("Loading YOLOv8 weights from %s (device=%s)", weights, device or "auto")
    logger.info("  torch.cuda.is_available=%s cuda.device_count=%d",
                torch.cuda.is_available(), torch.cuda.device_count())
    if device and device.startswith("cuda") and not torch.cuda.is_available():
        logger.warning("Requested device=%s but CUDA is not available — falling back to CPU.",
                       device)
    # cudnn benchmark picks the fastest conv algorithm for a given input shape
    # and reuses it on subsequent calls — valuable here since every clip hits
    # the same imgsz.
    torch.backends.cudnn.benchmark = True
    model = YOLO(str(weights))
    if device:
        model.to(device)
    # Confirm the underlying torch model actually landed on CUDA. If this
    # reports cpu, ultralytics silently ignored the .to() call.
    try:
        first_param = next(model.model.parameters())
        logger.info("  model weights on device=%s dtype=%s",
                    first_param.device, first_param.dtype)
    except Exception:
        pass
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
            vec = extract_yolo_features(tmp, model, imgsz=args.imgsz, device=args.device)
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
            vec = extract_yolo_features(v, model, imgsz=args.imgsz, device=args.device)
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


def _make_r2_client_from_env():
    """Build a raw boto3 S3 client from env vars — no Settings/DB dependency."""
    import boto3
    from botocore.config import Config

    account_id = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ.get("R2_BUCKET_NAME") or os.environ.get("R2_BUCKET")
    if not bucket:
        raise RuntimeError("Set R2_BUCKET_NAME (or R2_BUCKET) in the environment.")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "adaptive"},
            max_pool_connections=64,
        ),
    )
    return client, bucket


def _download_clip(client, bucket: str, key: str) -> Path:
    """Single-threaded download (boto3's multipart TransferManager spawns
    10+ internal threads per file, overflowing the connection pool)."""
    from boto3.s3.transfer import TransferConfig
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    try:
        client.download_fileobj(
            bucket, key, tmp,
            Config=TransferConfig(use_threads=False, multipart_threshold=1024 ** 4),
        )
    finally:
        tmp.close()
    return Path(tmp.name)


def _run_from_manifest(args: argparse.Namespace, model) -> None:
    """DB-free mode for Colab: read a JSON manifest and pull clips from R2.

    Overlaps R2 downloads with GPU inference via a bounded prefetch pool so the
    GPU isn't idle between network-bound steps.
    """
    entries = json.loads(args.manifest.read_text())
    if not entries:
        logger.error("Manifest %s is empty.", args.manifest)
        sys.exit(1)

    client, bucket = _make_r2_client_from_env()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pending, skipped = [], 0
    for e in entries:
        out = args.output_dir / f"{e['clip_id']}_yolo.npz"
        if out.exists() and not args.force:
            skipped += 1
        else:
            pending.append(e)

    if not pending:
        logger.info("All %d manifest entries already processed.", skipped)
        return

    # Semaphore bounds how many downloaded-but-not-yet-consumed clips can sit
    # on disk, so a slow GPU can't let the prefetch queue fill local storage.
    slot = Semaphore(args.prefetch)

    def _download(entry: dict) -> tuple[str, Path, float]:
        slot.acquire()
        t0 = time.perf_counter()
        try:
            path = _download_clip(client, bucket, entry["r2_key_front"])
            return entry["clip_id"], path, time.perf_counter() - t0
        except Exception:
            slot.release()
            raise

    extracted = failed = 0
    n_debug = 5  # per-stage timing for the first N clips
    with ThreadPoolExecutor(max_workers=args.download_workers) as pool:
        futures = {pool.submit(_download, e): e for e in pending}
        pbar = tqdm(as_completed(futures), total=len(pending),
                    desc="YOLO features", unit="clip")
        for fut in pbar:
            entry = futures[fut]
            clip_id = entry["clip_id"]
            tmp_path = None
            try:
                clip_id, tmp_path, dl_s = fut.result()
                t1 = time.perf_counter()
                timings: dict = {}
                vec = extract_yolo_features(tmp_path, model, imgsz=args.imgsz,
                                            device=args.device, timings=timings)
                infer_s = time.perf_counter() - t1
                save_yolo_features(clip_id, vec, out_dir=args.output_dir)
                extracted += 1
                if extracted <= n_debug:
                    logger.info(
                        "  [timing %d] dl=%.2fs decode=%.2fs predict=%.2fs "
                        "(%d frames) total_infer=%.2fs",
                        extracted, dl_s,
                        timings.get("decode_s", 0.0),
                        timings.get("predict_s", 0.0),
                        timings.get("n_frames", 0),
                        infer_s,
                    )
            except Exception as exc:
                logger.error("Failed on %s (%s): %s", clip_id, entry["r2_key_front"], exc)
                failed += 1
            finally:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink()
                slot.release()

    logger.info("── YOLO Feature Extraction (manifest) ──────")
    logger.info("  Extracted: %d", extracted)
    logger.info("  Skipped:   %d", skipped)
    logger.info("  Failed:    %d", failed)
    logger.info("  Workers:   %d download / prefetch=%d", args.download_workers, args.prefetch)
    logger.info("  Output:    %s/", args.output_dir)


def main() -> None:
    args = parse_args()
    if not any([args.all, args.clip_id, args.input_dir, args.manifest]):
        logger.error("Specify --all, --clip-id <UUID>, --input-dir <path>, or --manifest <json>")
        sys.exit(1)

    model = _load_model(args.weights, args.device)
    _warmup_model(model, args.imgsz, args.device)

    if args.manifest:
        _run_from_manifest(args, model)
    elif args.input_dir:
        _run_from_dir(args, model)
    else:
        _run_from_db(args, model)


if __name__ == "__main__":
    main()

"""
Feature sequence builder for the deep learning model.

Combines YOLOv8 per-frame object detections with optical flow to produce
a temporal sequence of feature vectors suitable for LSTM input.

Per-frame feature vector (13 dimensions):
  Index  Feature
  ─────  ──────────────────────────────────────────────────────
  0      n_vehicles        — count of cars, trucks, buses, motorcycles
  1      n_pedestrians     — count of persons
  2      n_cyclists        — count of bicycles
  3      n_traffic_lights  — count of traffic light detections
  4      n_stop_signs      — count of stop sign detections
  5      vehicle_proximity — max(bbox_area / frame_area) for vehicles (0–1)
  6      pedestrian_proximity — max(bbox_area / frame_area) for pedestrians
  7      flow_magnitude    — mean optical flow magnitude (normalised by /20)
  8      flow_sin          — sin(mean flow direction) for circular encoding
  9      flow_cos          — cos(mean flow direction)
  10     motion_blur       — Laplacian variance normalised by /500
  11     edge_density      — Canny edge pixel fraction (0–1)
  12     speed_proxy       — 90th-percentile optical flow magnitude / 20

COCO class IDs used:
  0=person, 1=bicycle, 2=car, 3=motorcycle, 5=bus, 7=truck,
  9=traffic light, 11=stop sign

Sequence layout:
  Each clip is processed with a sliding window of SEQUENCE_LENGTH frames
  and STEP_SIZE overlap, producing shape (n_windows, SEQUENCE_LENGTH, 13).
  Windows are saved as data/processed/{clip_id}_dl_features.npz.
"""

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SEQUENCE_LENGTH = 30    # frames per window (~1 sec at 30fps)
STEP_SIZE = 15          # 50% overlap
FEATURE_DIM = 13

# COCO class ID sets
_VEHICLE_IDS = {2, 3, 5, 7}          # car, motorcycle, bus, truck
_PEDESTRIAN_IDS = {0}                 # person
_CYCLIST_IDS = {1}                    # bicycle
_TRAFFIC_LIGHT_IDS = {9}
_STOP_SIGN_IDS = {11}

_FB_PARAMS = dict(pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


class SequenceBuilder:
    """
    Builds LSTM-ready feature sequences from a dashcam video.

    YOLOv8 is loaded once per instance and reused across frames. The model
    is loaded lazily on first call to avoid startup overhead when the class
    is imported without running inference.

    Args:
        yolo_model_path: Path to YOLOv8 weights (.pt file).
        device: Torch device string ('cpu', 'cuda', 'mps').
        confidence: Minimum detection confidence threshold.
    """

    def __init__(
        self,
        yolo_model_path: str = "models/yolov8m.pt",
        device: str = "cpu",
        confidence: float = 0.25,
    ) -> None:
        self.yolo_model_path = yolo_model_path
        self.device = device
        self.confidence = confidence
        self._yolo = None   # loaded lazily

    def _load_yolo(self):
        """Lazily load YOLOv8 model on first use."""
        if self._yolo is None:
            try:
                from ultralytics import YOLO
                self._yolo = YOLO(self.yolo_model_path)
                logger.info("Loaded YOLOv8 from %s", self.yolo_model_path)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load YOLOv8 from {self.yolo_model_path}. "
                    "Run: pip install ultralytics and ensure weights exist."
                ) from exc
        return self._yolo

    def build_sequences(self, video_path: str | Path) -> np.ndarray:
        """
        Extract feature sequences from a single video file.

        Processes every frame: runs YOLOv8 detection and computes optical
        flow between consecutive frames. Assembles a sliding-window sequence
        array suitable for LSTM input.

        Args:
            video_path: Path to a local MP4 file.

        Returns:
            Float32 array of shape (n_windows, SEQUENCE_LENGTH, FEATURE_DIM).
            Returns empty array of shape (0, SEQUENCE_LENGTH, FEATURE_DIM)
            if the video is too short to form a single window.
        """
        video_path = Path(video_path)
        yolo = self._load_yolo()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        frame_features: list[np.ndarray] = []
        prev_gray: np.ndarray | None = None

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                if w > 640:
                    frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA)
                    h, w = frame.shape[:2]

                frame_area = h * w

                # ── YOLOv8 detection ──────────────────────────────────────
                results = yolo(frame, verbose=False, conf=self.confidence)[0]
                boxes = results.boxes

                feat = self._detection_features(boxes, frame_area, w, h)

                # ── Optical flow ──────────────────────────────────────────
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, **_FB_PARAMS)
                    fx, fy = flow[..., 0], flow[..., 1]
                    mag = np.sqrt(fx**2 + fy**2)
                    mean_mag = float(np.mean(mag))
                    p90_mag = float(np.percentile(mag, 90))
                    angle = float(np.mean(np.arctan2(fy, fx)))
                else:
                    mean_mag = p90_mag = angle = 0.0

                # ── Motion blur + edge density ─────────────────────────────
                blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                edges = cv2.Canny(gray, 50, 150)
                edge_frac = float(np.sum(edges > 0)) / max(frame_area, 1)

                # ── Assemble feature vector ───────────────────────────────
                flow_vec = np.array([
                    mean_mag / 20.0,
                    np.sin(angle),
                    np.cos(angle),
                    min(blur / 500.0, 1.0),
                    min(edge_frac, 1.0),
                    min(p90_mag / 20.0, 1.0),
                ], dtype=np.float32)

                frame_vec = np.concatenate([feat, flow_vec])  # (13,)
                frame_features.append(frame_vec)
                prev_gray = gray
        finally:
            cap.release()

        if len(frame_features) < SEQUENCE_LENGTH:
            logger.warning(
                "%s too short (%d frames) for sequence length %d",
                video_path.name, len(frame_features), SEQUENCE_LENGTH,
            )
            return np.empty((0, SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)

        frames_arr = np.stack(frame_features, axis=0)   # (N, 13)
        return self._sliding_windows(frames_arr)

    def _detection_features(
        self, boxes, frame_area: int, frame_w: int, frame_h: int
    ) -> np.ndarray:
        """
        Convert YOLOv8 detection boxes to a 7-dim feature vector.

        Args:
            boxes: ultralytics Boxes object from a detection result.
            frame_area: Total frame pixel count (h * w).
            frame_w, frame_h: Frame dimensions.

        Returns:
            Float32 array of shape (7,):
            [n_vehicles, n_pedestrians, n_cyclists, n_lights, n_signs,
             vehicle_proximity, pedestrian_proximity]
        """
        n_vehicles = n_pedestrians = n_cyclists = n_lights = n_signs = 0
        vehicle_prox = pedestrian_prox = 0.0

        if boxes is not None and len(boxes) > 0:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            xyxy = boxes.xyxy.cpu().numpy()   # (N, 4)

            for cls_id, box in zip(cls_ids, xyxy):
                bw = box[2] - box[0]
                bh = box[3] - box[1]
                area_ratio = (bw * bh) / max(frame_area, 1)

                if cls_id in _VEHICLE_IDS:
                    n_vehicles += 1
                    vehicle_prox = max(vehicle_prox, area_ratio)
                elif cls_id in _PEDESTRIAN_IDS:
                    n_pedestrians += 1
                    pedestrian_prox = max(pedestrian_prox, area_ratio)
                elif cls_id in _CYCLIST_IDS:
                    n_cyclists += 1
                elif cls_id in _TRAFFIC_LIGHT_IDS:
                    n_lights += 1
                elif cls_id in _STOP_SIGN_IDS:
                    n_signs += 1

        # Normalise counts (clip at 10 to keep bounded)
        return np.array([
            min(n_vehicles, 10) / 10.0,
            min(n_pedestrians, 10) / 10.0,
            min(n_cyclists, 10) / 10.0,
            min(n_lights, 5) / 5.0,
            min(n_signs, 3) / 3.0,
            min(vehicle_prox, 1.0),
            min(pedestrian_prox, 1.0),
        ], dtype=np.float32)

    def _sliding_windows(self, frames: np.ndarray) -> np.ndarray:
        """
        Convert a frame sequence into sliding windows.

        Args:
            frames: Shape (N, FEATURE_DIM).

        Returns:
            Shape (n_windows, SEQUENCE_LENGTH, FEATURE_DIM).
        """
        n = len(frames)
        windows = []
        for start in range(0, n - SEQUENCE_LENGTH + 1, STEP_SIZE):
            windows.append(frames[start : start + SEQUENCE_LENGTH])
        return np.stack(windows, axis=0) if windows else np.empty(
            (0, SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32
        )


def save_dl_features(
    clip_id: str,
    sequences: np.ndarray,
    output_dir: Path = Path("data/processed"),
) -> Path:
    """Save DL feature sequences to a compressed .npz archive."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{clip_id}_dl_features.npz"
    np.savez_compressed(str(path), sequences=sequences)
    return path


def load_dl_features(
    clip_id: str,
    features_dir: Path = Path("data/processed"),
) -> np.ndarray | None:
    """Load DL feature sequences. Returns None if file not found."""
    path = features_dir / f"{clip_id}_dl_features.npz"
    if not path.exists():
        return None
    return np.load(str(path))["sequences"]

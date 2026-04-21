"""
Celery tasks for async video processing.

Production pipeline (single model — classical ML):
  1. Download front video from R2 to a temp file
  2. Extract features (optical-flow + object statistics)
  3. Run classical anomaly classifier → (is_anomaly, probability, features)
  4. Compute per-clip driving score
  5. Generate Claude AI explanation for any flagged anomaly
  6. Persist Anomaly + Score rows to PostgreSQL
  7. Update clip.processing_status → DONE (or FAILED on error)

The classical model has F1=0.97 vs user labels on this dataset and was
chosen as the deployed model. The baseline and LSTM live in scripts/models
for the written report's three-model comparison but do not run on uploads.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _probe_duration_seconds(video_path: str | Path) -> float | None:
    """Return the video's duration in seconds using OpenCV (frames / fps).

    Returns None on any probing failure — callers must fall back gracefully.
    """
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        if fps <= 0 or frames <= 0:
            return None
        return float(frames / fps)
    finally:
        cap.release()


def _locate_peak_window(
    video_path: str | Path,
    window_seconds: float = 5.0,
    stride_seconds: float = 1.0,
) -> tuple[float, float] | None:
    """Locate the time window with the highest average optical-flow magnitude.

    The classical classifier runs at the whole-clip level (binary yes/no), so
    it doesn't tell us *when* within the clip the event happens. This helper
    re-scans the already-downloaded video with a downsampled optical-flow
    pass and picks the sliding window with peak magnitude. Used to populate
    the anomaly's (timestamp_start, timestamp_end) so the UI can seek to
    the event instead of playing the whole clip.

    Returns None on any failure so the caller can fall back to whole-clip
    timestamps.
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0:
            return None

        # Subsample at ~10 fps for speed — we only need coarse motion signal.
        target_fps = 10.0
        stride_frames = max(1, int(round(fps / target_fps)))
        fb_params = dict(pyr_scale=0.5, levels=2, winsize=15, iterations=2, poly_n=5, poly_sigma=1.2, flags=0)

        prev_gray = None
        magnitudes: list[float] = []
        idx = -1
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            idx += 1
            if idx % stride_frames != 0:
                continue
            h, w = frame.shape[:2]
            if w > 320:
                frame = cv2.resize(frame, (320, int(h * 320 / w)), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, **fb_params)
                mag = float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)))
                magnitudes.append(mag)
            prev_gray = gray
    finally:
        cap.release()

    if len(magnitudes) < 2:
        return None

    # Each magnitude entry represents 1/target_fps seconds
    sec_per_sample = 1.0 / target_fps
    w_samples = max(1, int(round(window_seconds / sec_per_sample)))
    s_samples = max(1, int(round(stride_seconds / sec_per_sample)))

    n = len(magnitudes)
    if n <= w_samples:
        # Whole-clip is shorter than window — return full span
        return (0.0, n * sec_per_sample)

    mags = np.array(magnitudes, dtype=np.float32)
    best_start = 0
    best_score = -1.0
    for s in range(0, n - w_samples + 1, s_samples):
        score = float(np.mean(mags[s : s + w_samples]))
        if score > best_score:
            best_score = score
            best_start = s

    start_s = best_start * sec_per_sample
    end_s = (best_start + w_samples) * sec_per_sample
    return (round(start_s, 2), round(end_s, 2))


def _recalculate_overall_score(db) -> None:
    """Recompute the OverallDriverScore from all classical per-clip scores."""
    from api.models.db_models import ModelType, OverallDriverScore, Score
    from scripts.scoring import ClipScoreResult, compute_overall_score

    score_rows = db.query(Score).filter(Score.model_type == ModelType.CLASSICAL).all()
    if not score_rows:
        return

    clip_scores = [
        ClipScoreResult(
            clip_id=str(row.clip_id),
            score=row.score,
            grade=row.grade,
            anomaly_count=row.anomaly_count,
            deduction_breakdown={},
        )
        for row in score_rows
    ]
    result = compute_overall_score(clip_scores)

    existing = db.query(OverallDriverScore).first()
    if existing:
        existing.model_type = ModelType.CLASSICAL
        existing.score = result.score
        existing.grade = result.grade
        existing.clips_analyzed = result.clips_analyzed
        existing.breakdown = result.breakdown
        existing.calculated_at = datetime.now(timezone.utc)
    else:
        db.add(OverallDriverScore(
            model_type=ModelType.CLASSICAL,
            score=result.score,
            grade=result.grade,
            clips_analyzed=result.clips_analyzed,
            breakdown=result.breakdown,
            calculated_at=datetime.now(timezone.utc),
        ))
    db.commit()
    logger.info(
        "Overall score recalculated: %.1f %s (%d clips)",
        result.score, result.grade, result.clips_analyzed,
    )


_FEATURE_TO_TYPE = {
    # Sudden single-frame motion peaks → rapid deceleration, i.e. hard braking.
    "flow_max":                "hard_braking",
    "flow_p95":                "hard_braking",
    "flow_p90":                "hard_braking",
    "window_max_peak":         "hard_braking",
    "max_consecutive_spikes":  "hard_braking",
    # Erratic steering shows up as high variance in optical-flow direction.
    "direction_variance":      "harsh_cornering",
    # Frequent direction flips indicate crossing / weaving between lanes.
    "direction_change_rate":   "lane_departure",
    # Repeated magnitude spikes / sustained elevated motion → aggressive
    # maneuvering (abrupt lane changes, darting through traffic).
    "n_magnitude_spikes":      "aggressive_lane_change",
    "spike_rate":              "aggressive_lane_change",
    "window_n_flagged":        "aggressive_lane_change",
    "window_max_mean":         "aggressive_lane_change",
    "window_max_std":          "aggressive_lane_change",
    "flow_std":                "aggressive_lane_change",
    "flow_mean":               "aggressive_lane_change",
    "flow_p75":                "aggressive_lane_change",
    # Blur/edge noise isn't a useful behavioural signal on its own.
    "blur_mean":               "other",
    "blur_min":                "other",
    "edge_density_std":        "other",
    "edge_density_max_change": "other",
}


# Minimum z-score required to commit to a specific behavioural type. Below
# this, every feature is essentially "within the training distribution" and
# picking hard_braking / harsh_cornering / etc is just noise — the binary
# classifier still flagged the clip, but the motion signature isn't strong
# enough to name a category. Events like traffic violations (no motion
# signature in the 19 features) typically land here.
_TYPE_COMMIT_THRESHOLD = 1.0


def _anomaly_type_from_zscores(zscores: dict) -> tuple[str, bool]:
    """
    Pick an AnomalyType based on which feature is most anomalous *for this clip*.

    `zscores` is produced by ClassicalClassifier.predict() — each entry is the
    feature's value after StandardScaler, i.e. a z-score relative to the
    training distribution.

    Returns (type_str, ambiguous). `ambiguous=True` means no feature crossed
    the commit threshold, so the caller should treat the type as a best-effort
    guess (typically "other") rather than a confident classification.
    """
    if not zscores:
        return "other", True

    ranked = sorted(zscores.items(), key=lambda kv: kv[1], reverse=True)
    max_z = ranked[0][1]

    # If nothing is meaningfully deviant, the motion signature is too weak
    # to name a specific behaviour. Report "other" and flag as ambiguous so
    # the UI can surface it honestly.
    if max_z < _TYPE_COMMIT_THRESHOLD:
        return "other", True

    # Walk ranked features until we find one that maps to a real behaviour
    # (skip blur/edge_density which map to "other"). Only consider features
    # whose z-score is still above the commit threshold.
    for name, z in ranked:
        if z < _TYPE_COMMIT_THRESHOLD:
            break
        atype = _FEATURE_TO_TYPE.get(name, "other")
        if atype != "other":
            return atype, False

    return "other", True


@celery_app.task(name="api.tasks.video_tasks.process_clip", bind=True, max_retries=3)
def process_clip(self, clip_id: str) -> dict:
    """
    Async pipeline for a single clip — classical ML only.

    Downloads the front video, extracts features, runs the classical
    classifier, scores the clip, generates an AI explanation if flagged,
    and persists the results.
    """
    from api.database import SessionLocal
    from api.models.db_models import (
        Anomaly,
        AnomalyType,
        Clip,
        ModelType,
        ProcessingStatus,
        Score,
    )
    from scripts.build_features import extract_features, save_features
    from scripts.models.classical import ClassicalAnomalyClassifier
    from scripts.scoring import AnomalyInput
    from scripts.scoring import AnomalyType as ScoringAnomalyType
    from scripts.scoring import score_clip as compute_score
    from scripts.genai import AnomalyExplainer

    db = SessionLocal()
    tmp_path = None

    try:
        clip = db.query(Clip).filter(Clip.id == uuid.UUID(clip_id)).first()
        if not clip:
            logger.error("Clip %s not found", clip_id)
            return {"clip_id": clip_id, "error": "not found"}

        clip.processing_status = ProcessingStatus.PROCESSING
        db.commit()

        # 1. Download
        from api.storage.r2_client import R2Client
        r2 = R2Client()
        tmp_path = r2.download_to_temp(clip.r2_key_front)
        logger.info("[%s] Downloaded to %s", clip.filename_prefix, tmp_path)

        # Backfill clip duration if we've never probed it. Needed so the UI
        # can display real timestamps (anomaly timestamp_end uses this value)
        # and the library's duration column stops showing "—".
        if clip.duration_seconds is None:
            probed = _probe_duration_seconds(tmp_path)
            if probed is not None:
                clip.duration_seconds = probed
                db.commit()

        # 2. Feature extraction (cache by clip_id)
        cached = Path(f"data/processed/{clip_id}_features.npz")
        if not cached.exists():
            features = extract_features(tmp_path)
            save_features(clip_id, features)

        # 3. Classical classifier
        clf = ClassicalAnomalyClassifier()
        result = clf.predict(clip_id)
        logger.info(
            "[%s] Classical: anomaly=%s prob=%.3f",
            clip.filename_prefix, result.is_anomaly, result.anomaly_probability,
        )

        # Wipe prior rows for this clip across all model types so a reprocess
        # leaves only the current single-model output visible.
        for mt in (ModelType.BASELINE, ModelType.CLASSICAL, ModelType.DEEP_LEARNING):
            db.query(Anomaly).filter(
                Anomaly.clip_id == clip.id, Anomaly.model_type == mt
            ).delete()
            db.query(Score).filter(
                Score.clip_id == clip.id, Score.model_type == mt
            ).delete()

        # 4. Build anomaly row (if flagged) + score
        anomaly_rows: list[Anomaly] = []
        score_inputs: list[AnomalyInput] = []

        if result.is_anomaly:
            type_str, ambiguous_type = _anomaly_type_from_zscores(result.feature_zscores)
            try:
                atype = AnomalyType(type_str)
                scoring_atype = ScoringAnomalyType(type_str)
            except ValueError:
                atype = AnomalyType.OTHER
                scoring_atype = ScoringAnomalyType.OTHER
                ambiguous_type = True

            top_zscores = dict(
                sorted(result.feature_zscores.items(),
                       key=lambda x: x[1], reverse=True)[:5]
            )

            # Localize the event within the clip so the UI can seek to it,
            # rather than marking the whole clip.
            peak = _locate_peak_window(tmp_path)
            if peak is None:
                ts_start, ts_end = 0.0, float(clip.duration_seconds or 0.0)
            else:
                ts_start, ts_end = peak

            score_inputs.append(AnomalyInput(scoring_atype, result.anomaly_probability))
            anomaly_rows.append(Anomaly(
                clip_id=clip.id,
                model_type=ModelType.CLASSICAL,
                anomaly_type=atype,
                severity=result.anomaly_probability,
                confidence=result.anomaly_probability,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
                score_impact=0.0,
                detection_metadata={
                    "top_deviant_features": {k: round(v, 3) for k, v in top_zscores.items()},
                    "top_global_importances": dict(
                        sorted(result.feature_importances.items(),
                               key=lambda x: x[1], reverse=True)[:5]
                    ),
                    "peak_window_seconds": [ts_start, ts_end],
                    "ambiguous_type": ambiguous_type,
                    "type_commit_threshold": _TYPE_COMMIT_THRESHOLD,
                },
            ))

        score_result = compute_score(clip_id, score_inputs)

        # Attach per-anomaly deduction for UI display
        for row in anomaly_rows:
            row.score_impact = round(score_result.deduction_breakdown.get(row.anomaly_type.value, 0.0), 2)

        # 5. AI explanation (only if flagged)
        if anomaly_rows:
            try:
                explainer = AnomalyExplainer()
                anomaly_dicts = [
                    {
                        "anomaly_id": str(uuid.uuid4()),
                        "anomaly_type": row.anomaly_type.value,
                        "severity": row.severity,
                        "score_impact": row.score_impact,
                        "detected_objects": [],
                        "timestamp_start": row.timestamp_start,
                        "timestamp_end": row.timestamp_end,
                    }
                    for row in anomaly_rows
                ]
                explanations = explainer.explain_batch(anomaly_dicts)
                for row, exp in zip(anomaly_rows, explanations):
                    row.ai_explanation = (
                        f"{exp.explanation}\n\n"
                        f"Recommendation: {exp.recommendation}\n\n"
                        f"{exp.score_impact_text}"
                    )
            except Exception as exc:
                logger.warning("[%s] AI explanation failed: %s", clip.filename_prefix, exc)

        # 6. Persist
        for row in anomaly_rows:
            db.add(row)
        db.add(Score(
            clip_id=clip.id,
            model_type=ModelType.CLASSICAL,
            score=score_result.score,
            grade=score_result.grade,
            anomaly_count=score_result.anomaly_count,
        ))

        clip.processing_status = ProcessingStatus.DONE
        clip.processed_at = datetime.now(timezone.utc)
        clip.processing_error = None
        db.commit()

        # 7. Overall score
        try:
            _recalculate_overall_score(db)
        except Exception as exc:
            logger.warning("[%s] Overall score recalc failed: %s", clip.filename_prefix, exc)

        logger.info(
            "[%s] Done — score=%.1f grade=%s anomalies=%d",
            clip.filename_prefix, score_result.score,
            score_result.grade, len(anomaly_rows),
        )
        return {
            "clip_id": clip_id,
            "score": score_result.score,
            "grade": score_result.grade,
            "anomaly_count": len(anomaly_rows),
        }

    except Exception as exc:
        logger.error("[%s] Processing failed: %s", clip_id, exc, exc_info=True)
        try:
            from api.models.db_models import ProcessingStatus
            clip.processing_status = ProcessingStatus.FAILED
            clip.processing_error = str(exc)
            db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink()


@celery_app.task(name="api.tasks.video_tasks.process_all_pending")
def process_all_pending() -> dict:
    """Enqueue process_clip tasks for all clips with PENDING status."""
    from api.database import SessionLocal
    from api.models.db_models import Clip, ProcessingStatus

    db = SessionLocal()
    try:
        pending = db.query(Clip).filter(
            Clip.processing_status == ProcessingStatus.PENDING
        ).all()
        count = len(pending)
        for clip in pending:
            process_clip.delay(str(clip.id))
            clip.processing_status = ProcessingStatus.PROCESSING
        db.commit()
        logger.info("Enqueued %d clips for processing", count)
        return {"enqueued": count}
    finally:
        db.close()

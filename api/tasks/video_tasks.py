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


def _anomaly_type_from_features(feature_importances: dict) -> str:
    """
    Pick an AnomalyType from the classical model's top feature importances.

    The classical model is a single binary classifier; mapping its top-weighted
    feature to a human-readable category keeps the UI's detail labels useful
    instead of showing every flagged clip as "OTHER".
    """
    if not feature_importances:
        return "other"
    top = max(feature_importances, key=feature_importances.get)
    t = top.lower()
    if "brake" in t or "decel" in t:
        return "hard_braking"
    if "lane" in t or "lateral" in t:
        return "lane_departure"
    if "corner" in t or "yaw" in t or "turn" in t:
        return "harsh_cornering"
    if "speed" in t or "accel" in t:
        return "aggressive_lane_change"
    return "other"


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
            type_str = _anomaly_type_from_features(result.feature_importances)
            try:
                atype = AnomalyType(type_str)
                scoring_atype = ScoringAnomalyType(type_str)
            except ValueError:
                atype = AnomalyType.OTHER
                scoring_atype = ScoringAnomalyType.OTHER

            score_inputs.append(AnomalyInput(scoring_atype, result.anomaly_probability))
            anomaly_rows.append(Anomaly(
                clip_id=clip.id,
                model_type=ModelType.CLASSICAL,
                anomaly_type=atype,
                severity=result.anomaly_probability,
                confidence=result.anomaly_probability,
                timestamp_start=0.0,
                timestamp_end=float(clip.duration_seconds or 0.0),
                score_impact=0.0,
                detection_metadata={
                    "top_features": dict(
                        sorted(result.feature_importances.items(),
                               key=lambda x: x[1], reverse=True)[:5]
                    ),
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

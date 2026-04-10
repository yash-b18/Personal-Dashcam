"""
Celery tasks for async video processing.

Full pipeline for a single clip:
  1. Download front video from R2 to a temp file
  2. Run optical flow baseline detector
  3. Map baseline anomaly windows → AnomalyType via heuristic
  4. Compute per-clip driving score
  5. Generate Claude AI explanation for each anomaly
  6. Persist Anomaly + Score rows to PostgreSQL
  7. Update clip.processing_status → DONE (or FAILED on error)
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _recalculate_overall_score(db) -> None:
    """
    Recompute the OverallDriverScore from all per-clip Score rows.
    Called automatically after every clip finishes processing.
    """
    from api.models.db_models import ModelType, OverallDriverScore, Score
    from scripts.scoring import ClipScoreResult, compute_overall_score, assign_grade

    # Fetch all baseline scores (one per clip)
    score_rows = (
        db.query(Score)
        .filter(Score.model_type == ModelType.BASELINE)
        .all()
    )
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

    # Upsert OverallDriverScore (keep only one row)
    existing = db.query(OverallDriverScore).first()
    if existing:
        existing.score = result.score
        existing.grade = result.grade
        existing.clips_analyzed = result.clips_analyzed
        existing.breakdown = result.breakdown
        existing.calculated_at = datetime.now(timezone.utc)
    else:
        db.add(OverallDriverScore(
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


def _heuristic_anomaly_type(window: dict, clip_severity: float) -> str:
    """
    Map a baseline anomaly window to an AnomalyType based on heuristics.

    Peak magnitude and severity give a coarse signal:
    - Very high peak + high severity → near_miss
    - High peak → hard_braking
    - Moderate variance → lane_departure
    - Low peak but flagged → harsh_cornering
    """
    peak = window.get("peak_magnitude", 0.0)
    sev = window.get("severity", clip_severity)

    if sev >= 0.8 and peak >= 25.0:
        return "near_miss"
    elif peak >= 20.0:
        return "hard_braking"
    elif peak >= 15.0:
        return "lane_departure"
    elif sev >= 0.5:
        return "harsh_cornering"
    return "other"


@celery_app.task(name="api.tasks.video_tasks.process_clip", bind=True, max_retries=3)
def process_clip(self, clip_id: str) -> dict:
    """
    Full async pipeline for a single clip.

    Downloads the front video, runs the baseline detector, scores the clip,
    generates AI explanations, and persists everything to the DB.
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
    from scripts.models.baseline import OpticalFlowBaseline
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

        # ── 1. Download front video ───────────────────────────────────────
        from api.storage.r2_client import R2Client
        r2 = R2Client()
        tmp_path = r2.download_to_temp(clip.r2_key_front)
        logger.info("[%s] Downloaded to %s", clip.filename_prefix, tmp_path)

        # ── 2. Run baseline detector ──────────────────────────────────────
        detector = OpticalFlowBaseline()
        result = detector.predict(tmp_path)
        logger.info(
            "[%s] Baseline: anomaly=%s severity=%.3f windows=%d",
            clip.filename_prefix, result.is_anomaly,
            result.severity, len(result.anomaly_windows),
        )

        # ── 3. Map windows → DB Anomaly rows ──────────────────────────────
        anomaly_inputs: list[AnomalyInput] = []
        anomaly_db_rows: list[Anomaly] = []

        if result.is_anomaly and result.anomaly_windows:
            for w in result.anomaly_windows:
                atype_str = _heuristic_anomaly_type(w, result.severity)
                try:
                    atype = AnomalyType(atype_str)
                    scoring_atype = ScoringAnomalyType(atype_str)
                except ValueError:
                    atype = AnomalyType.OTHER
                    scoring_atype = ScoringAnomalyType.OTHER

                win_severity = float(w.get("severity", result.severity))
                anomaly_inputs.append(AnomalyInput(scoring_atype, win_severity))

                anomaly_db_rows.append(Anomaly(
                    clip_id=clip.id,
                    model_type=ModelType.BASELINE,
                    anomaly_type=atype,
                    severity=win_severity,
                    confidence=min(win_severity + 0.1, 1.0),
                    timestamp_start=float(w.get("start_second", 0.0)),
                    timestamp_end=float(w.get("end_second", 0.0)),
                    score_impact=0.0,   # filled after scoring
                    detection_metadata={
                        "peak_magnitude": w.get("peak_magnitude"),
                        "total_frames": result.total_frames,
                        "fps": result.fps,
                    },
                ))

        # ── 4. Score the clip ─────────────────────────────────────────────
        score_result = compute_score(clip_id, anomaly_inputs)

        # Back-fill score_impact per anomaly type
        type_impacts = dict(score_result.deduction_breakdown)
        type_counts: dict[str, int] = {}
        for row in anomaly_db_rows:
            k = row.anomaly_type.value
            type_counts[k] = type_counts.get(k, 0) + 1

        for row in anomaly_db_rows:
            k = row.anomaly_type.value
            impact = type_impacts.get(k, 0.0)
            count = type_counts.get(k, 1)
            row.score_impact = round(impact / count, 2)

        # ── 5. Generate AI explanations ───────────────────────────────────
        if anomaly_db_rows:
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
                for row in anomaly_db_rows
            ]
            try:
                explanations = explainer.explain_batch(anomaly_dicts)
                for row, exp in zip(anomaly_db_rows, explanations):
                    row.ai_explanation = (
                        f"{exp.explanation}\n\n"
                        f"Recommendation: {exp.recommendation}\n\n"
                        f"{exp.score_impact_text}"
                    )
            except Exception as exc:
                logger.warning("[%s] AI explanation failed: %s", clip.filename_prefix, exc)

        # ── 6. Persist to DB ──────────────────────────────────────────────
        # Remove old baseline results for this clip to avoid duplicates
        db.query(Anomaly).filter(
            Anomaly.clip_id == clip.id, Anomaly.model_type == ModelType.BASELINE
        ).delete()
        db.query(Score).filter(
            Score.clip_id == clip.id, Score.model_type == ModelType.BASELINE
        ).delete()

        for row in anomaly_db_rows:
            db.add(row)

        score_row = Score(
            clip_id=clip.id,
            model_type=ModelType.BASELINE,
            score=score_result.score,
            grade=score_result.grade,
            anomaly_count=score_result.anomaly_count,
        )
        db.add(score_row)

        # ── 7. Update clip status ─────────────────────────────────────────
        clip.processing_status = ProcessingStatus.DONE
        clip.processed_at = datetime.now(timezone.utc)
        clip.processing_error = None
        db.commit()

        # ── 8. Recalculate overall driver score ───────────────────────────
        try:
            _recalculate_overall_score(db)
        except Exception as exc:
            logger.warning("[%s] Overall score recalc failed: %s", clip.filename_prefix, exc)

        logger.info(
            "[%s] Done — score=%.1f grade=%s anomalies=%d",
            clip.filename_prefix, score_result.score,
            score_result.grade, len(anomaly_db_rows),
        )
        return {
            "clip_id": clip_id,
            "score": score_result.score,
            "grade": score_result.grade,
            "anomaly_count": len(anomaly_db_rows),
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

"""
Score endpoints.

GET  /scores/overall        — current overall driver score + grade
GET  /scores/history        — per-clip score history for trend charts
GET  /scores/dashboard      — all dashboard data in one call
POST /scores/recalculate    — recompute overall score from DB clip scores

The production pipeline runs the classical model only; all endpoints return
classical-derived scores and anomaly counts.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from api.database import get_db
from api.models.db_models import Anomaly, Clip, ModelType, OverallDriverScore, Score
from api.schemas import (
    AnomalyBreakdown,
    ClipScoreHistory,
    DashboardResponse,
    OverallScoreResponse,
    ScoreHistoryResponse,
)

router = APIRouter(prefix="/scores", tags=["scores"])

_MODEL = ModelType.CLASSICAL


@router.get("/overall", response_model=OverallScoreResponse)
def get_overall_score(db: Session = Depends(get_db)) -> OverallScoreResponse:
    """Return the most recently computed overall driver score."""
    row = (
        db.query(OverallDriverScore)
        .order_by(OverallDriverScore.calculated_at.desc())
        .first()
    )
    if row:
        return OverallScoreResponse(
            score=row.score,
            grade=row.grade,
            clips_analyzed=row.clips_analyzed,
            breakdown=row.breakdown or {},
            calculated_at=row.calculated_at,
        )
    return _compute_and_cache_overall(db)


@router.get("/history", response_model=ScoreHistoryResponse)
def get_score_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ScoreHistoryResponse:
    """Per-clip score history ordered chronologically (for trend charts)."""
    rows = (
        db.query(Score, Clip)
        .join(Clip, Score.clip_id == Clip.id)
        .filter(Score.model_type == _MODEL)
        .order_by(Clip.recorded_at.asc().nullslast(), Score.calculated_at.asc())
        .limit(limit)
        .all()
    )
    history = [
        ClipScoreHistory(
            clip_id=score.clip_id,
            filename_prefix=clip.filename_prefix,
            recorded_at=clip.recorded_at,
            score=score.score,
            grade=score.grade,
            anomaly_count=score.anomaly_count,
            calculated_at=score.calculated_at,
        )
        for score, clip in rows
    ]
    return ScoreHistoryResponse(history=history, total=len(history))


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    trend_limit: int = Query(30, ge=5, le=1000),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    """All data needed for the driver dashboard in a single request."""
    overall = get_overall_score(db=db)

    recent_count = db.query(Anomaly).filter(Anomaly.model_type == _MODEL).count()
    clips_with_anomalies = (
        db.query(Anomaly.clip_id)
        .filter(Anomaly.model_type == _MODEL)
        .distinct()
        .count()
    )
    breakdown_rows = (
        db.query(
            Anomaly.anomaly_type,
            func.count(Anomaly.id).label("cnt"),
            func.sum(Anomaly.score_impact).label("total_impact"),
        )
        .filter(Anomaly.model_type == _MODEL)
        .group_by(Anomaly.anomaly_type)
        .all()
    )
    breakdown = [
        AnomalyBreakdown(
            anomaly_type=r.anomaly_type.value,
            count=r.cnt,
            total_score_impact=round(r.total_impact or 0.0, 2),
        )
        for r in breakdown_rows
    ]

    trend = get_score_history(limit=trend_limit, db=db)

    return DashboardResponse(
        overall_score=overall.score,
        grade=overall.grade,
        clips_analyzed=overall.clips_analyzed,
        recent_anomaly_count=recent_count,
        clips_with_anomalies=clips_with_anomalies,
        anomaly_breakdown=breakdown,
        score_trend=trend.history,
    )


@router.post("/recalculate", response_model=OverallScoreResponse)
def recalculate_overall(db: Session = Depends(get_db)) -> OverallScoreResponse:
    """Force recompute the overall score from all classical per-clip scores."""
    return _compute_and_cache_overall(db)


# ── Internal helpers ───────────────────────────────────────────────────────────


def _compute_and_cache_overall(db: Session) -> OverallScoreResponse:
    """Compute overall score from classical clip scores and persist."""
    from scripts.scoring import (
        ClipScoreResult,
        compute_overall_score,
    )

    score_rows = (
        db.query(Score, Clip)
        .join(Clip, Score.clip_id == Clip.id)
        .filter(Score.model_type == _MODEL)
        .order_by(Clip.recorded_at.asc().nullslast(), Score.calculated_at.asc())
        .all()
    )

    if not score_rows:
        return OverallScoreResponse(
            score=100.0, grade="A", clips_analyzed=0, breakdown={}
        )

    clip_scores = [
        ClipScoreResult(
            clip_id=str(score.clip_id),
            score=score.score,
            grade=score.grade,
            anomaly_count=score.anomaly_count,
        )
        for score, clip in score_rows
    ]
    result = compute_overall_score(clip_scores)

    overall_row = OverallDriverScore(
        model_type=_MODEL,
        score=result.score,
        grade=result.grade,
        clips_analyzed=result.clips_analyzed,
        breakdown=result.breakdown,
    )
    db.add(overall_row)
    db.commit()
    db.refresh(overall_row)

    return OverallScoreResponse(
        score=overall_row.score,
        grade=overall_row.grade,
        clips_analyzed=overall_row.clips_analyzed,
        breakdown=overall_row.breakdown or {},
        calculated_at=overall_row.calculated_at,
    )

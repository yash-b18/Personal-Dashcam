"""
Score endpoints.

GET /scores/overall        — current overall driver score + grade
GET /scores/history        — per-clip score history for trend charts
GET /scores/dashboard      — all dashboard data in one call
POST /scores/recalculate   — recompute overall score from DB clip scores
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

_DEFAULT_MODEL = ModelType.BASELINE


@router.get("/overall", response_model=OverallScoreResponse)
def get_overall_score(
    model_type: str = Query("baseline"),
    db: Session = Depends(get_db),
) -> OverallScoreResponse:
    """
    Return the most recently computed overall driver score.

    Uses the latest OverallDriverScore row for the requested model_type.
    If none exists, computes on the fly from per-clip scores.
    """
    try:
        mt = ModelType(model_type)
    except ValueError:
        mt = _DEFAULT_MODEL

    row = (
        db.query(OverallDriverScore)
        .filter(OverallDriverScore.model_type == mt)
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

    # No cached row — compute from per-clip scores
    return _compute_and_cache_overall(mt, db)


@router.get("/history", response_model=ScoreHistoryResponse)
def get_score_history(
    model_type: str = Query("baseline"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ScoreHistoryResponse:
    """
    Return per-clip score history ordered chronologically (for trend charts).
    """
    try:
        mt = ModelType(model_type)
    except ValueError:
        mt = _DEFAULT_MODEL

    rows = (
        db.query(Score, Clip)
        .join(Clip, Score.clip_id == Clip.id)
        .filter(Score.model_type == mt)
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
    model_type: str = Query("baseline"),
    trend_limit: int = Query(30, ge=5, le=100),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    """
    Return all data needed for the driver dashboard in a single request.

    Includes: overall score, anomaly breakdown by type, and score trend.
    """
    try:
        mt = ModelType(model_type)
    except ValueError:
        mt = _DEFAULT_MODEL

    overall = get_overall_score(model_type=model_type, db=db)

    # Anomaly count in last 30 days
    recent_count = db.query(Anomaly).filter(Anomaly.model_type == mt).count()

    # Breakdown by anomaly type
    breakdown_rows = (
        db.query(
            Anomaly.anomaly_type,
            func.count(Anomaly.id).label("cnt"),
            func.sum(Anomaly.score_impact).label("total_impact"),
        )
        .filter(Anomaly.model_type == mt)
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

    trend = get_score_history(model_type=model_type, limit=trend_limit, db=db)

    return DashboardResponse(
        overall_score=overall.score,
        grade=overall.grade,
        clips_analyzed=overall.clips_analyzed,
        recent_anomaly_count=recent_count,
        anomaly_breakdown=breakdown,
        score_trend=trend.history,
    )


@router.post("/recalculate", response_model=OverallScoreResponse)
def recalculate_overall(
    model_type: str = Query("baseline"),
    db: Session = Depends(get_db),
) -> OverallScoreResponse:
    """Force recompute the overall score from all per-clip scores in the DB."""
    try:
        mt = ModelType(model_type)
    except ValueError:
        mt = _DEFAULT_MODEL
    return _compute_and_cache_overall(mt, db)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _compute_and_cache_overall(mt: ModelType, db: Session) -> OverallScoreResponse:
    """Compute overall score from clip scores and persist to DB."""
    from scripts.scoring import (
        ClipScoreResult,
        assign_grade,
        compute_overall_score,
    )

    score_rows = (
        db.query(Score, Clip)
        .join(Clip, Score.clip_id == Clip.id)
        .filter(Score.model_type == mt)
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

    # Persist
    overall_row = OverallDriverScore(
        model_type=mt,
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

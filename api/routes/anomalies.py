"""
Anomaly endpoints.

GET  /anomalies            — paginated list with filters
GET  /anomalies/{id}       — detail with AI explanation and presigned clip URL

The production pipeline only runs the classical model, so listings are
filtered to classical detections.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models.db_models import Anomaly, Clip, ModelType
from api.schemas import AnomalyDetail, AnomalyListResponse, AnomalySummary
from api.storage.r2_client import R2Client

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

_MODEL = ModelType.CLASSICAL


@router.get("", response_model=AnomalyListResponse)
def list_anomalies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    anomaly_type: str | None = Query(None),
    min_severity: float = Query(0.0, ge=0.0, le=1.0),
    clip_id: uuid.UUID | None = Query(None, description="Filter by clip"),
    db: Session = Depends(get_db),
) -> AnomalyListResponse:
    """List classical-model anomalies with optional filters."""
    query = db.query(Anomaly).filter(Anomaly.model_type == _MODEL)
    if clip_id is not None:
        query = query.filter(Anomaly.clip_id == clip_id)
    if anomaly_type:
        query = query.filter(Anomaly.anomaly_type == anomaly_type)
    if min_severity > 0:
        query = query.filter(Anomaly.severity >= min_severity)

    total = query.count()
    rows = (
        query.order_by(Anomaly.detected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AnomalyListResponse(
        anomalies=[
            AnomalySummary(
                id=a.id,
                clip_id=a.clip_id,
                model_type=a.model_type.value,
                anomaly_type=a.anomaly_type.value,
                severity=a.severity,
                confidence=a.confidence,
                timestamp_start=a.timestamp_start,
                timestamp_end=a.timestamp_end,
                score_impact=a.score_impact,
                ai_explanation=a.ai_explanation,
                detected_at=a.detected_at,
            )
            for a in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{anomaly_id}", response_model=AnomalyDetail)
def get_anomaly(anomaly_id: uuid.UUID, db: Session = Depends(get_db)) -> AnomalyDetail:
    """Get full anomaly detail including AI explanation and presigned video URL."""
    anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    clip = db.query(Clip).filter(Clip.id == anomaly.clip_id).first()
    front_url = None
    rear_url = None
    if clip:
        try:
            r2 = R2Client()
            front_url = r2.presigned_url(clip.r2_key_front, expires_in=3600)
            rear_url = r2.presigned_url(clip.r2_key_rear, expires_in=3600)
        except Exception:
            pass

    return AnomalyDetail(
        id=anomaly.id,
        clip_id=anomaly.clip_id,
        model_type=anomaly.model_type.value,
        anomaly_type=anomaly.anomaly_type.value,
        severity=anomaly.severity,
        confidence=anomaly.confidence,
        timestamp_start=anomaly.timestamp_start,
        timestamp_end=anomaly.timestamp_end,
        score_impact=anomaly.score_impact,
        ai_explanation=anomaly.ai_explanation,
        detected_at=anomaly.detected_at,
        detection_metadata=anomaly.detection_metadata,
        clip_filename=clip.filename_prefix if clip else None,
        front_url=front_url,
        rear_url=rear_url,
    )

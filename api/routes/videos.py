"""
Video / clip endpoints.

GET  /videos               — paginated list of all clips with scores
GET  /videos/{clip_id}     — full clip detail with presigned video URLs
POST /videos/{clip_id}/process  — enqueue Celery processing task
POST /videos/process-all   — enqueue all pending clips
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.models.db_models import Anomaly, Clip, ModelType, ProcessingStatus, Score
from api.schemas import (
    ClipDetail,
    ClipListResponse,
    ClipSummary,
    ProcessAllResponse,
    ProcessResponse,
)
from api.storage.r2_client import R2Client

router = APIRouter(prefix="/videos", tags=["videos"])


def _r2() -> R2Client:
    return R2Client()


def _clip_summary(clip: Clip, db: Session, r2: R2Client | None = None) -> ClipSummary:
    score_row = (
        db.query(Score)
        .filter(Score.clip_id == clip.id, Score.model_type == ModelType.BASELINE)
        .order_by(Score.calculated_at.desc())
        .first()
    )
    anomaly_count = db.query(Anomaly).filter(Anomaly.clip_id == clip.id).count()
    front_url = None
    if r2:
        try:
            front_url = r2.presigned_url(clip.r2_key_front, expires_in=3600)
        except Exception:
            pass
    return ClipSummary(
        id=clip.id,
        filename_prefix=clip.filename_prefix,
        duration_seconds=clip.duration_seconds,
        recorded_at=clip.recorded_at,
        processing_status=clip.processing_status.value,
        score=score_row.score if score_row else None,
        grade=score_row.grade if score_row else None,
        anomaly_count=anomaly_count,
        front_url=front_url,
    )


@router.get("", response_model=ClipListResponse)
def list_clips(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by processing_status"),
    db: Session = Depends(get_db),
) -> ClipListResponse:
    """List all clips with pagination and optional status filter."""
    query = db.query(Clip)
    if status:
        try:
            ps = ProcessingStatus(status)
            query = query.filter(Clip.processing_status == ps)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    total = query.count()
    clips = (
        query.order_by(Clip.recorded_at.desc().nullslast(), Clip.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    r2 = _r2()
    return ClipListResponse(
        clips=[_clip_summary(c, db, r2) for c in clips],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{clip_id}", response_model=ClipDetail)
def get_clip(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> ClipDetail:
    """Get full clip details including presigned front + rear video URLs (1 hour TTL)."""
    clip = db.query(Clip).filter(Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    r2 = _r2()
    score_row = (
        db.query(Score)
        .filter(Score.clip_id == clip.id, Score.model_type == ModelType.BASELINE)
        .order_by(Score.calculated_at.desc())
        .first()
    )
    anomaly_count = db.query(Anomaly).filter(Anomaly.clip_id == clip.id).count()

    try:
        front_url = r2.presigned_url(clip.r2_key_front, expires_in=3600)
    except Exception:
        front_url = None
    try:
        rear_url = r2.presigned_url(clip.r2_key_rear, expires_in=3600)
    except Exception:
        rear_url = None

    return ClipDetail(
        id=clip.id,
        filename_prefix=clip.filename_prefix,
        duration_seconds=clip.duration_seconds,
        recorded_at=clip.recorded_at,
        processing_status=clip.processing_status.value,
        score=score_row.score if score_row else None,
        grade=score_row.grade if score_row else None,
        anomaly_count=anomaly_count,
        front_url=front_url,
        rear_url=rear_url,
        r2_key_front=clip.r2_key_front,
        r2_key_rear=clip.r2_key_rear,
        processing_error=clip.processing_error,
        created_at=clip.created_at,
        processed_at=clip.processed_at,
    )


@router.post("/{clip_id}/process", response_model=ProcessResponse)
def process_clip_endpoint(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> ProcessResponse:
    """Enqueue the clip for async ML processing via Celery."""
    clip = db.query(Clip).filter(Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.processing_status == ProcessingStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Clip is already being processed")

    from api.tasks.video_tasks import process_clip as celery_task
    task = celery_task.delay(str(clip_id))
    clip.processing_status = ProcessingStatus.PROCESSING
    db.commit()
    return ProcessResponse(task_id=task.id, clip_id=clip_id)


@router.post("/process-all", response_model=ProcessAllResponse)
def process_all_pending(db: Session = Depends(get_db)) -> ProcessAllResponse:
    """Enqueue all PENDING clips for processing."""
    from api.tasks.video_tasks import process_clip as celery_task

    pending = db.query(Clip).filter(Clip.processing_status == ProcessingStatus.PENDING).all()
    for clip in pending:
        celery_task.delay(str(clip.id))
        clip.processing_status = ProcessingStatus.PROCESSING
    db.commit()
    return ProcessAllResponse(enqueued=len(pending))

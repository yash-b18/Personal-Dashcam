"""
Video / clip endpoints.

GET  /videos               — paginated list of all clips with scores
GET  /videos/{clip_id}     — full clip detail with presigned video URLs
POST /videos/upload        — upload a new video and auto-enqueue processing
POST /videos/{clip_id}/process  — enqueue Celery processing task
POST /videos/process-all   — enqueue all pending clips
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB hard cap
UPLOAD_PREFIX = "uploads/"


def _r2() -> R2Client:
    return R2Client()


def _classical_score_row(clip_id, db: Session) -> Score | None:
    """Return the most recent classical score row for this clip (the only
    model that runs in production)."""
    return (
        db.query(Score)
        .filter(Score.clip_id == clip_id, Score.model_type == ModelType.CLASSICAL)
        .order_by(Score.calculated_at.desc())
        .first()
    )


def _clip_summary(clip: Clip, db: Session, r2: R2Client | None = None) -> ClipSummary:
    score_row = _classical_score_row(clip.id, db)
    anomaly_count = (
        db.query(Anomaly)
        .filter(Anomaly.clip_id == clip.id, Anomaly.model_type == ModelType.CLASSICAL)
        .count()
    )
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
    score_row = _classical_score_row(clip.id, db)
    anomaly_count = (
        db.query(Anomaly)
        .filter(Anomaly.clip_id == clip.id, Anomaly.model_type == ModelType.CLASSICAL)
        .count()
    )

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


@router.post("/upload", response_model=ProcessResponse, status_code=201)
async def upload_video(
    file: UploadFile = File(..., description="Video file (mp4/mov/m4v/avi)"),
    db: Session = Depends(get_db),
) -> ProcessResponse:
    """
    Upload a user-provided dashcam clip, persist it to R2, and enqueue async processing.

    The clip enters the pipeline immediately and its anomalies contribute to the
    overall driver score once the three-model pipeline finishes. Front and rear
    both point at the uploaded object (single-camera uploads are the common case).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Accepted: {', '.join(sorted(ALLOWED_VIDEO_EXT))}",
        )

    # Sanitize the prefix so it's safe as an R2 key fragment + DB column
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", Path(file.filename).stem)[:200] or "upload"
    clip_id = uuid.uuid4()
    filename_prefix = f"{safe_stem}_{clip_id.hex[:8]}"
    r2_key = f"{UPLOAD_PREFIX}{filename_prefix}{suffix}"

    # Stream body into R2 without buffering the full file in memory
    try:
        size = 0
        chunk = await file.read(1024 * 1024)
        if not chunk:
            raise HTTPException(status_code=400, detail="Empty file")
        # Peek-then-upload pattern: use a wrapper that enforces max size
        r2 = R2Client()
        # Rewind by using an in-memory buffer for the already-read chunk + remainder
        import io
        buf = io.BytesIO()
        while chunk:
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit",
                )
            buf.write(chunk)
            chunk = await file.read(1024 * 1024)
        buf.seek(0)
        r2.upload_fileobj(buf, r2_key, content_type=file.content_type or "video/mp4")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("R2 upload failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    # Persist clip row — front + rear both reference the uploaded object
    clip = Clip(
        id=clip_id,
        r2_key_front=r2_key,
        r2_key_rear=r2_key,
        filename_prefix=filename_prefix,
        file_size_bytes_front=size,
        file_size_bytes_rear=size,
        recorded_at=datetime.now(timezone.utc),
        processing_status=ProcessingStatus.PROCESSING,
    )
    db.add(clip)
    db.commit()

    # Enqueue processing — results will feed into the overall driver score recalc
    from api.tasks.video_tasks import process_clip as celery_task
    task = celery_task.delay(str(clip_id))

    logger.info("Uploaded %s (%d bytes) → clip %s, task %s", r2_key, size, clip_id, task.id)
    return ProcessResponse(task_id=task.id, clip_id=clip_id)


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

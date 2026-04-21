"""
Labeling endpoints — powers the admin clip review interface.

GET  /labels/queue         — next batch of unlabeled clips with presigned URLs
POST /labels/{clip_id}     — submit thumbs up/down label
PUT  /labels/{clip_id}     — update an existing label
GET  /labels/{clip_id}     — get the label for a clip
DELETE /labels/{clip_id}   — remove a label (returns clip to queue)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models.db_models import Clip, Label
from api.schemas import LabelQueueItem, LabelQueueResponse, LabelResponse, LabelSubmit
from api.storage.r2_client import R2Client

router = APIRouter(prefix="/labels", tags=["labels"])


def _presign(r2: R2Client, key: str) -> str | None:
    try:
        return r2.presigned_url(key, expires_in=7200)
    except Exception:
        return None


@router.get("/queue", response_model=LabelQueueResponse)
def get_label_queue(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> LabelQueueResponse:
    """
    Return the next batch of clips that have not yet been labeled.

    Clips are ordered by recorded_at (oldest first) so reviewers
    progress through the dataset chronologically.
    """
    labeled_ids = db.query(Label.clip_id).subquery()
    query = db.query(Clip).filter(Clip.id.notin_(labeled_ids))
    total_unlabeled = query.count()

    clips = (
        query.order_by(Clip.recorded_at.asc().nullslast(), Clip.created_at.asc())
        .limit(limit)
        .all()
    )

    r2 = R2Client()
    items = [
        LabelQueueItem(
            id=c.id,
            filename_prefix=c.filename_prefix,
            duration_seconds=c.duration_seconds,
            recorded_at=c.recorded_at,
            front_url=_presign(r2, c.r2_key_front),
            rear_url=_presign(r2, c.r2_key_rear),
        )
        for c in clips
    ]
    return LabelQueueResponse(clips=items, total_unlabeled=total_unlabeled)


@router.post("/{clip_id}", response_model=LabelResponse, status_code=201)
def submit_label(
    clip_id: uuid.UUID,
    body: LabelSubmit,
    db: Session = Depends(get_db),
) -> LabelResponse:
    """
    Submit a thumbs up (is_anomaly=true) or thumbs down (false) label for a clip.

    If a label already exists for this clip it is overwritten.
    """
    clip = db.query(Clip).filter(Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    existing = db.query(Label).filter(Label.clip_id == clip_id).first()
    if existing:
        existing.is_anomaly = body.is_anomaly
        existing.anomaly_types = body.anomaly_types
        existing.reason = body.reason
        label = existing
    else:
        label = Label(
            clip_id=clip_id,
            is_anomaly=body.is_anomaly,
            anomaly_types=body.anomaly_types,
            reason=body.reason,
        )
        db.add(label)

    db.commit()
    db.refresh(label)
    return LabelResponse(
        clip_id=label.clip_id,
        is_anomaly=label.is_anomaly,
        anomaly_types=label.anomaly_types,
        reason=label.reason,
        labeled_at=label.labeled_at,
    )


@router.put("/{clip_id}", response_model=LabelResponse)
def update_label(
    clip_id: uuid.UUID,
    body: LabelSubmit,
    db: Session = Depends(get_db),
) -> LabelResponse:
    """Update an existing label."""
    label = db.query(Label).filter(Label.clip_id == clip_id).first()
    if not label:
        raise HTTPException(status_code=404, detail="No label found for this clip")

    label.is_anomaly = body.is_anomaly
    label.anomaly_types = body.anomaly_types
    label.reason = body.reason
    db.commit()
    db.refresh(label)
    return LabelResponse(
        clip_id=label.clip_id,
        is_anomaly=label.is_anomaly,
        anomaly_types=label.anomaly_types,
        reason=label.reason,
        labeled_at=label.labeled_at,
    )


@router.get("/{clip_id}", response_model=LabelResponse)
def get_label(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> LabelResponse:
    """Retrieve the label for a specific clip."""
    label = db.query(Label).filter(Label.clip_id == clip_id).first()
    if not label:
        raise HTTPException(status_code=404, detail="No label found for this clip")
    return LabelResponse(
        clip_id=label.clip_id,
        is_anomaly=label.is_anomaly,
        anomaly_types=label.anomaly_types,
        reason=label.reason,
        labeled_at=label.labeled_at,
    )


@router.delete("/{clip_id}", status_code=204)
def delete_label(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Remove a label, returning the clip to the review queue."""
    label = db.query(Label).filter(Label.clip_id == clip_id).first()
    if not label:
        raise HTTPException(status_code=404, detail="No label found for this clip")
    db.delete(label)
    db.commit()

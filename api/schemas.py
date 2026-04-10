"""
Pydantic response/request schemas for the DashcamIQ API.

Separate from ORM models — these are the shapes the API surfaces to clients.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Clips / Videos ────────────────────────────────────────────────────────────

class ClipSummary(BaseModel):
    id: uuid.UUID
    filename_prefix: str
    duration_seconds: float | None = None
    recorded_at: datetime | None = None
    processing_status: str
    score: float | None = None
    grade: str | None = None
    anomaly_count: int = 0
    front_url: str | None = None    # presigned R2 URL

    model_config = {"from_attributes": True}


class ClipDetail(ClipSummary):
    r2_key_front: str
    r2_key_rear: str
    processing_error: str | None = None
    created_at: datetime
    processed_at: datetime | None = None
    rear_url: str | None = None


class ClipListResponse(BaseModel):
    clips: list[ClipSummary]
    total: int
    page: int
    page_size: int


# ── Anomalies ──────────────────────────────────────────────────────────────────

class AnomalySummary(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    model_type: str
    anomaly_type: str
    severity: float
    confidence: float
    timestamp_start: float
    timestamp_end: float
    score_impact: float
    ai_explanation: str | None = None
    detected_at: datetime

    model_config = {"from_attributes": True}


class AnomalyDetail(AnomalySummary):
    detection_metadata: dict[str, Any] | None = None
    clip_filename: str | None = None
    front_url: str | None = None
    rear_url: str | None = None


class AnomalyListResponse(BaseModel):
    anomalies: list[AnomalySummary]
    total: int
    page: int
    page_size: int


# ── Labels ─────────────────────────────────────────────────────────────────────

class LabelQueueItem(BaseModel):
    id: uuid.UUID
    filename_prefix: str
    duration_seconds: float | None
    recorded_at: datetime | None
    front_url: str | None
    rear_url: str | None

    model_config = {"from_attributes": True}


class LabelQueueResponse(BaseModel):
    clips: list[LabelQueueItem]
    total_unlabeled: int


class LabelSubmit(BaseModel):
    is_anomaly: bool
    anomaly_types: list[str] | None = Field(default=None)
    reason: str | None = Field(default=None, max_length=1000)


class LabelResponse(BaseModel):
    clip_id: uuid.UUID
    is_anomaly: bool
    anomaly_types: list[str] | None
    reason: str | None
    labeled_at: datetime

    model_config = {"from_attributes": True}


# ── Scores ─────────────────────────────────────────────────────────────────────

class OverallScoreResponse(BaseModel):
    score: float
    grade: str
    clips_analyzed: int
    breakdown: dict[str, float] = {}
    calculated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClipScoreHistory(BaseModel):
    clip_id: uuid.UUID
    filename_prefix: str
    recorded_at: datetime | None
    score: float
    grade: str
    anomaly_count: int
    calculated_at: datetime

    model_config = {"from_attributes": True}


class ScoreHistoryResponse(BaseModel):
    history: list[ClipScoreHistory]
    total: int


class AnomalyBreakdown(BaseModel):
    anomaly_type: str
    count: int
    total_score_impact: float


class DashboardResponse(BaseModel):
    overall_score: float
    grade: str
    clips_analyzed: int
    recent_anomaly_count: int
    anomaly_breakdown: list[AnomalyBreakdown]
    score_trend: list[ClipScoreHistory]   # last N clips for chart


# ── Processing ─────────────────────────────────────────────────────────────────

class ProcessResponse(BaseModel):
    task_id: str
    clip_id: uuid.UUID
    status: str = "queued"


class ProcessAllResponse(BaseModel):
    enqueued: int
    status: str = "queued"

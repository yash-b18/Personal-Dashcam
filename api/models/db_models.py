"""
SQLAlchemy ORM models for DashcamIQ.

Tables:
    clips           — Paired front/rear dashcam video records
    labels          — Human annotations from the labeling interface
    anomalies       — Model-detected anomaly events
    scores          — Per-clip driving scores from each model
    overall_scores  — Aggregate driver scores across all clips
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from api.database import Base


class ProcessingStatus(str, enum.Enum):
    """Processing pipeline state for a clip."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ModelType(str, enum.Enum):
    """Which model produced a result."""

    BASELINE = "baseline"
    CLASSICAL = "classical"
    DEEP_LEARNING = "deep_learning"


class AnomalyType(str, enum.Enum):
    """Categories of detected driving anomalies."""

    HARD_BRAKING = "hard_braking"
    HARD_ACCELERATION = "hard_acceleration"
    NEAR_MISS = "near_miss"
    LANE_DEPARTURE = "lane_departure"
    TRAFFIC_VIOLATION = "traffic_violation"
    TAILGATING = "tailgating"
    AGGRESSIVE_LANE_CHANGE = "aggressive_lane_change"
    HARSH_CORNERING = "harsh_cornering"
    DISTRACTED_DRIVING = "distracted_driving"
    OTHER = "other"


class Clip(Base):
    """
    Represents one paired set of front + rear dashcam video files.

    Each dashcam segment is stored as two separate R2 objects (front/rear).
    A clip is the atomic unit of analysis and labeling.
    """

    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    r2_key_front: Mapped[str] = mapped_column(String(512), nullable=False)
    r2_key_rear: Mapped[str] = mapped_column(String(512), nullable=False)
    filename_prefix: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size_bytes_front: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes_rear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    label: Mapped["Label | None"] = relationship(
        "Label", back_populates="clip", uselist=False
    )
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="clip")
    scores: Mapped[list["Score"]] = relationship("Score", back_populates="clip")

    def __repr__(self) -> str:
        return f"<Clip id={self.id} prefix={self.filename_prefix} status={self.processing_status}>"


class Label(Base):
    """
    Human annotation from the admin labeling interface.

    One label per clip. Stores whether an anomaly was observed,
    what type(s) it was, and a free-text reason from the reviewer.
    """

    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clips.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # JSON array of AnomalyType values
    anomaly_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    clip: Mapped["Clip"] = relationship("Clip", back_populates="label")

    def __repr__(self) -> str:
        return f"<Label clip_id={self.clip_id} is_anomaly={self.is_anomaly}>"


class Anomaly(Base):
    """
    A specific anomaly event detected by a model within a clip.

    Multiple anomalies can exist per clip (one per detected event,
    one per model type). Stores the exact timestamp window, severity,
    and the Claude-generated explanation.
    """

    __tablename__ = "anomalies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_type: Mapped[ModelType] = mapped_column(
        Enum(ModelType), nullable=False, index=True
    )
    anomaly_type: Mapped[AnomalyType] = mapped_column(
        Enum(AnomalyType), nullable=False, index=True
    )
    severity: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 – 1.0
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 – 1.0
    timestamp_start: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # seconds into clip
    timestamp_end: Mapped[float] = mapped_column(Float, nullable=False)
    score_impact: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # points deducted
    # JSON blob: detected objects, optical flow stats, etc.
    detection_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    clip: Mapped["Clip"] = relationship("Clip", back_populates="anomalies")

    def __repr__(self) -> str:
        return f"<Anomaly clip_id={self.clip_id} type={self.anomaly_type} severity={self.severity:.2f}>"


class Score(Base):
    """
    Driving score for a single clip, produced by one model.

    Three rows can exist per clip (one per ModelType). The deployed
    model's score is used in the driver dashboard.
    """

    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_type: Mapped[ModelType] = mapped_column(Enum(ModelType), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0 – 100
    grade: Mapped[str] = mapped_column(String(1), nullable=False)  # A – F
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    clip: Mapped["Clip"] = relationship("Clip", back_populates="scores")

    def __repr__(self) -> str:
        return f"<Score clip_id={self.clip_id} model={self.model_type} score={self.score:.1f} grade={self.grade}>"


class OverallDriverScore(Base):
    """
    Aggregate driver score computed across all analyzed clips.

    Recalculated each time new clips are processed. Stores a snapshot
    of the overall score, grade, and how many clips were included.
    """

    __tablename__ = "overall_driver_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_type: Mapped[ModelType] = mapped_column(Enum(ModelType), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str] = mapped_column(String(1), nullable=False)
    clips_analyzed: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON: breakdown by anomaly type, score distribution stats
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<OverallDriverScore model={self.model_type} score={self.score:.1f} grade={self.grade}>"

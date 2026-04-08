"""
Driver scoring engine.

Converts raw anomaly detections into a 0–100 per-trip driving score
and aggregates scores across all clips into an overall driver score.

Scoring model:
  - Base score: 100 points
  - Deductions are applied per anomaly: deduction = severity * max_deduction[type]
  - Multiple anomalies of the same type in one clip are capped at 1.5x the base deduction
  - Final clip score = max(0, 100 - Σ deductions)
  - Overall score = exponentially weighted average (recent clips weighted more)
  - Grade: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F < 60

Implemented in: feature/scoring-genai
"""

from dataclasses import dataclass, field
from enum import Enum


class AnomalyType(str, Enum):
    """Anomaly categories mirroring the DB enum."""
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


# Maximum point deduction per anomaly type (at severity = 1.0)
MAX_DEDUCTIONS: dict[AnomalyType, float] = {
    AnomalyType.HARD_BRAKING: 15.0,
    AnomalyType.HARD_ACCELERATION: 10.0,
    AnomalyType.NEAR_MISS: 25.0,
    AnomalyType.LANE_DEPARTURE: 20.0,
    AnomalyType.TRAFFIC_VIOLATION: 30.0,
    AnomalyType.TAILGATING: 15.0,
    AnomalyType.AGGRESSIVE_LANE_CHANGE: 15.0,
    AnomalyType.HARSH_CORNERING: 10.0,
    AnomalyType.DISTRACTED_DRIVING: 20.0,
    AnomalyType.OTHER: 5.0,
}

GRADE_THRESHOLDS = {
    "A": 90.0,
    "B": 80.0,
    "C": 70.0,
    "D": 60.0,
}


@dataclass
class AnomalyInput:
    """Lightweight anomaly descriptor for scoring calculations."""
    anomaly_type: AnomalyType
    severity: float   # 0.0 – 1.0


@dataclass
class ClipScoreResult:
    """Scoring output for a single clip."""
    clip_id: str
    score: float
    grade: str
    anomaly_count: int
    deduction_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class OverallScoreResult:
    """Aggregate driver score across all clips."""
    score: float
    grade: str
    clips_analyzed: int
    breakdown: dict[str, float] = field(default_factory=dict)


def score_clip(clip_id: str, anomalies: list[AnomalyInput]) -> ClipScoreResult:
    """
    Compute a driving score for a single clip given its detected anomalies.

    Args:
        clip_id: UUID string of the clip.
        anomalies: List of detected anomalies with type and severity.

    Returns:
        ClipScoreResult with score, grade, and per-type breakdown.
    """
    raise NotImplementedError("Implemented in feature/scoring-genai")


def compute_overall_score(clip_scores: list[ClipScoreResult]) -> OverallScoreResult:
    """
    Aggregate per-clip scores into an overall driver score.

    Uses exponential weighting so recent clips have more influence.

    Args:
        clip_scores: All per-clip scores in chronological order (oldest first).

    Returns:
        OverallScoreResult with weighted average score and grade.
    """
    raise NotImplementedError("Implemented in feature/scoring-genai")


def assign_grade(score: float) -> str:
    """
    Assign a letter grade to a numeric score.

    Args:
        score: Float in [0, 100].

    Returns:
        Letter grade: A, B, C, D, or F.
    """
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return "F"

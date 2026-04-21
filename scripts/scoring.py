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
"""

from collections import defaultdict
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

# Cap: multiple anomalies of same type cannot deduct more than this multiplier
# of the base max deduction (prevents one rough trip wiping the score to 0)
SAME_TYPE_CAP_MULTIPLIER = 1.5

GRADE_THRESHOLDS = {
    "A": 90.0,
    "B": 80.0,
    "C": 70.0,
    "D": 60.0,
}

# Exponential decay factor for overall score weighting (higher = more recent-biased)
RECENCY_DECAY = 0.9


@dataclass
class AnomalyInput:
    """Lightweight anomaly descriptor for scoring calculations."""

    anomaly_type: AnomalyType
    severity: float  # 0.0 – 1.0


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

    Deductions per type are capped at SAME_TYPE_CAP_MULTIPLIER × MAX_DEDUCTIONS[type]
    so that repeated anomalies of the same kind don't dominate the score unfairly.

    Args:
        clip_id: UUID string of the clip.
        anomalies: List of detected anomalies with type and severity.

    Returns:
        ClipScoreResult with score (0–100), grade, and per-type breakdown.
    """
    # Accumulate raw deductions per type
    raw_by_type: dict[AnomalyType, float] = defaultdict(float)
    for anomaly in anomalies:
        atype = anomaly.anomaly_type
        severity = max(0.0, min(1.0, anomaly.severity))
        raw_by_type[atype] += severity * MAX_DEDUCTIONS.get(
            atype, MAX_DEDUCTIONS[AnomalyType.OTHER]
        )

    # Apply per-type cap and build breakdown
    breakdown: dict[str, float] = {}
    total_deduction = 0.0
    for atype, raw_deduction in raw_by_type.items():
        cap = (
            MAX_DEDUCTIONS.get(atype, MAX_DEDUCTIONS[AnomalyType.OTHER])
            * SAME_TYPE_CAP_MULTIPLIER
        )
        capped = min(raw_deduction, cap)
        breakdown[atype.value] = round(capped, 2)
        total_deduction += capped

    score = max(0.0, 100.0 - total_deduction)
    score = round(score, 2)

    return ClipScoreResult(
        clip_id=clip_id,
        score=score,
        grade=assign_grade(score),
        anomaly_count=len(anomalies),
        deduction_breakdown=breakdown,
    )


def compute_overall_score(clip_scores: list[ClipScoreResult]) -> OverallScoreResult:
    """
    Aggregate per-clip scores into an overall driver score.

    Uses exponential weighting so recent clips have more influence.
    clip_scores should be in chronological order (oldest first).

    Args:
        clip_scores: All per-clip scores in chronological order.

    Returns:
        OverallScoreResult with weighted average score and grade.
    """
    if not clip_scores:
        return OverallScoreResult(
            score=100.0, grade="A", clips_analyzed=0, breakdown={}
        )

    n = len(clip_scores)
    # Weight: most recent clip gets weight 1.0, then RECENCY_DECAY, RECENCY_DECAY^2, ...
    weights = [RECENCY_DECAY ** (n - 1 - i) for i in range(n)]
    total_weight = sum(weights)

    weighted_sum = sum(w * cs.score for w, cs in zip(weights, clip_scores))
    overall_score = round(weighted_sum / total_weight, 2)

    # Aggregate deduction breakdown (unweighted total per anomaly type)
    breakdown: dict[str, float] = defaultdict(float)
    for cs in clip_scores:
        for atype, deduction in cs.deduction_breakdown.items():
            breakdown[atype] += deduction
    breakdown = {k: round(v, 2) for k, v in breakdown.items()}

    return OverallScoreResult(
        score=overall_score,
        grade=assign_grade(overall_score),
        clips_analyzed=n,
        breakdown=dict(breakdown),
    )


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

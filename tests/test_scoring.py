"""
Unit tests for the scoring engine.

Tests are written against the interface defined in scripts/scoring.py.
Full implementations are verified once feature/scoring-genai is merged.
"""

import pytest

from scripts.scoring import AnomalyType, assign_grade


class TestAssignGrade:
    """Tests for the assign_grade helper (implemented in project-setup)."""

    def test_grade_a(self) -> None:
        assert assign_grade(95.0) == "A"
        assert assign_grade(90.0) == "A"

    def test_grade_b(self) -> None:
        assert assign_grade(85.0) == "B"
        assert assign_grade(80.0) == "B"

    def test_grade_c(self) -> None:
        assert assign_grade(75.0) == "C"
        assert assign_grade(70.0) == "C"

    def test_grade_d(self) -> None:
        assert assign_grade(65.0) == "D"
        assert assign_grade(60.0) == "D"

    def test_grade_f(self) -> None:
        assert assign_grade(59.9) == "F"
        assert assign_grade(0.0) == "F"

    def test_boundary_89_9(self) -> None:
        """89.9 should be B, not A."""
        assert assign_grade(89.9) == "B"


class TestAnomalyTypes:
    """Verify all anomaly types are defined."""

    def test_all_types_present(self) -> None:
        types = {t.value for t in AnomalyType}
        expected = {
            "hard_braking", "hard_acceleration", "near_miss",
            "lane_departure", "traffic_violation", "tailgating",
            "aggressive_lane_change", "harsh_cornering",
            "distracted_driving", "other",
        }
        assert expected.issubset(types)

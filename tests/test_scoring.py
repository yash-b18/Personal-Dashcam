"""
Unit tests for the scoring engine and genai explainer.

No DB, no API calls, no video files.
"""

import pytest

from scripts.scoring import (
    MAX_DEDUCTIONS,
    RECENCY_DECAY,
    SAME_TYPE_CAP_MULTIPLIER,
    AnomalyInput,
    AnomalyType,
    ClipScoreResult,
    OverallScoreResult,
    assign_grade,
    compute_overall_score,
    score_clip,
)


# ── assign_grade ───────────────────────────────────────────────────────────────

class TestAssignGrade:
    def test_a_at_90(self) -> None:
        assert assign_grade(90.0) == "A"

    def test_a_at_100(self) -> None:
        assert assign_grade(100.0) == "A"

    def test_b_at_80(self) -> None:
        assert assign_grade(80.0) == "B"

    def test_b_at_89(self) -> None:
        assert assign_grade(89.9) == "B"

    def test_c_at_70(self) -> None:
        assert assign_grade(70.0) == "C"

    def test_d_at_60(self) -> None:
        assert assign_grade(60.0) == "D"

    def test_f_at_59(self) -> None:
        assert assign_grade(59.9) == "F"

    def test_f_at_zero(self) -> None:
        assert assign_grade(0.0) == "F"

    def test_boundary_a_b(self) -> None:
        assert assign_grade(89.99) == "B"
        assert assign_grade(90.0) == "A"


class TestAnomalyTypes:
    def test_all_types_present(self) -> None:
        types = {t.value for t in AnomalyType}
        expected = {
            "hard_braking", "hard_acceleration", "near_miss",
            "lane_departure", "traffic_violation", "tailgating",
            "aggressive_lane_change", "harsh_cornering",
            "distracted_driving", "other",
        }
        assert expected.issubset(types)


# ── score_clip ─────────────────────────────────────────────────────────────────

class TestScoreClip:
    def test_no_anomalies_returns_100(self) -> None:
        result = score_clip("clip-1", [])
        assert result.score == 100.0
        assert result.grade == "A"
        assert result.anomaly_count == 0
        assert result.deduction_breakdown == {}

    def test_single_anomaly_deduction(self) -> None:
        result = score_clip("clip-1", [AnomalyInput(AnomalyType.NEAR_MISS, 1.0)])
        assert result.score == pytest.approx(75.0)
        assert result.deduction_breakdown["near_miss"] == pytest.approx(25.0)

    def test_severity_scales_deduction(self) -> None:
        result = score_clip("clip-1", [AnomalyInput(AnomalyType.NEAR_MISS, 0.5)])
        assert result.score == pytest.approx(87.5)

    def test_score_floored_at_zero(self) -> None:
        anomalies = [
            AnomalyInput(AnomalyType.TRAFFIC_VIOLATION, 1.0),
            AnomalyInput(AnomalyType.NEAR_MISS, 1.0),
            AnomalyInput(AnomalyType.LANE_DEPARTURE, 1.0),
            AnomalyInput(AnomalyType.HARD_BRAKING, 1.0),
            AnomalyInput(AnomalyType.DISTRACTED_DRIVING, 1.0),
        ]
        result = score_clip("clip-1", anomalies)
        assert result.score == 0.0

    def test_same_type_cap_applied(self) -> None:
        anomalies = [
            AnomalyInput(AnomalyType.NEAR_MISS, 1.0),
            AnomalyInput(AnomalyType.NEAR_MISS, 1.0),
        ]
        result = score_clip("clip-1", anomalies)
        cap = MAX_DEDUCTIONS[AnomalyType.NEAR_MISS] * SAME_TYPE_CAP_MULTIPLIER
        assert result.deduction_breakdown["near_miss"] == pytest.approx(cap)
        assert result.score == pytest.approx(100.0 - cap)

    def test_multiple_types_no_cap(self) -> None:
        anomalies = [
            AnomalyInput(AnomalyType.HARD_BRAKING, 1.0),
            AnomalyInput(AnomalyType.LANE_DEPARTURE, 1.0),
        ]
        result = score_clip("clip-1", anomalies)
        assert result.score == pytest.approx(65.0)

    def test_anomaly_count_correct(self) -> None:
        anomalies = [AnomalyInput(AnomalyType.TAILGATING, 0.5)] * 3
        result = score_clip("clip-1", anomalies)
        assert result.anomaly_count == 3

    def test_grade_assigned_correctly(self) -> None:
        result = score_clip("clip-1", [AnomalyInput(AnomalyType.OTHER, 0.1)])
        assert result.grade == assign_grade(result.score)

    def test_severity_clamped_above_1(self) -> None:
        r_normal = score_clip("c1", [AnomalyInput(AnomalyType.HARD_BRAKING, 1.0)])
        r_high   = score_clip("c2", [AnomalyInput(AnomalyType.HARD_BRAKING, 5.0)])
        assert r_normal.score == r_high.score

    def test_severity_clamped_below_0(self) -> None:
        r = score_clip("c1", [AnomalyInput(AnomalyType.HARD_BRAKING, -1.0)])
        assert r.score == 100.0

    def test_returns_clip_score_result(self) -> None:
        result = score_clip("clip-x", [])
        assert isinstance(result, ClipScoreResult)
        assert result.clip_id == "clip-x"


# ── compute_overall_score ──────────────────────────────────────────────────────

class TestComputeOverallScore:
    def _make_clip(self, clip_id: str, score: float, breakdown: dict | None = None) -> ClipScoreResult:
        return ClipScoreResult(
            clip_id=clip_id,
            score=score,
            grade=assign_grade(score),
            anomaly_count=0,
            deduction_breakdown=breakdown or {},
        )

    def test_empty_returns_100_A(self) -> None:
        result = compute_overall_score([])
        assert result.score == 100.0
        assert result.grade == "A"
        assert result.clips_analyzed == 0

    def test_single_clip(self) -> None:
        clips = [self._make_clip("c1", 75.0)]
        result = compute_overall_score(clips)
        assert result.score == pytest.approx(75.0)
        assert result.clips_analyzed == 1

    def test_uniform_scores(self) -> None:
        clips = [self._make_clip(f"c{i}", 80.0) for i in range(5)]
        result = compute_overall_score(clips)
        assert result.score == pytest.approx(80.0)

    def test_recent_clips_weighted_more(self) -> None:
        clips = [
            self._make_clip("old", 60.0),
            self._make_clip("recent", 100.0),
        ]
        result = compute_overall_score(clips)
        assert result.score > 80.0  # more than simple average

    def test_clips_analyzed_count(self) -> None:
        clips = [self._make_clip(f"c{i}", 85.0) for i in range(7)]
        result = compute_overall_score(clips)
        assert result.clips_analyzed == 7

    def test_returns_overall_score_result(self) -> None:
        result = compute_overall_score([self._make_clip("c1", 90.0)])
        assert isinstance(result, OverallScoreResult)

    def test_grade_matches_score(self) -> None:
        clips = [self._make_clip(f"c{i}", 70.0) for i in range(3)]
        result = compute_overall_score(clips)
        assert result.grade == assign_grade(result.score)

    def test_breakdown_aggregates_deductions(self) -> None:
        c1 = self._make_clip("c1", 85.0, {"hard_braking": 15.0})
        c2 = self._make_clip("c2", 80.0, {"hard_braking": 10.0, "tailgating": 10.0})
        result = compute_overall_score([c1, c2])
        assert result.breakdown["hard_braking"] == pytest.approx(25.0)
        assert "tailgating" in result.breakdown


# ── AnomalyExplainer (no real API calls) ──────────────────────────────────────

class TestAnomalyExplainer:
    def _make_explainer(self):
        from scripts.genai import AnomalyExplainer
        return AnomalyExplainer(api_key="fake-key-for-testing")

    def test_build_prompt_contains_anomaly_type(self) -> None:
        ex = self._make_explainer()
        prompt = ex._build_prompt(
            anomaly_type="hard_braking",
            severity=0.8,
            score_impact=12.0,
            detected_objects=["car", "pedestrian"],
            timestamp_start=5.0,
            timestamp_end=7.0,
        )
        assert "hard braking" in prompt
        assert "car" in prompt
        assert "pedestrian" in prompt

    def test_build_prompt_contains_severity_label(self) -> None:
        ex = self._make_explainer()
        prompt = ex._build_prompt(
            anomaly_type="near_miss",
            severity=0.9,
            score_impact=22.5,
            detected_objects=[],
            timestamp_start=0.0,
            timestamp_end=2.0,
        )
        assert "severe" in prompt

    def test_parse_response_valid_json(self) -> None:
        ex = self._make_explainer()
        raw = '{"explanation": "Foo.", "recommendation": "Bar.", "score_impact_text": "Baz."}'
        parsed = ex._parse_response(raw)
        assert parsed["explanation"] == "Foo."
        assert parsed["recommendation"] == "Bar."
        assert parsed["score_impact_text"] == "Baz."

    def test_parse_response_handles_markdown_fences(self) -> None:
        ex = self._make_explainer()
        raw = '```json\n{"explanation": "X.", "recommendation": "Y.", "score_impact_text": "Z."}\n```'
        parsed = ex._parse_response(raw)
        assert parsed["explanation"] == "X."

    def test_parse_response_fallback_on_bad_json(self) -> None:
        ex = self._make_explainer()
        parsed = ex._parse_response("not valid json at all")
        assert "explanation" in parsed
        assert "recommendation" in parsed
        assert "score_impact_text" in parsed

    def test_fallback_response_structure(self) -> None:
        ex = self._make_explainer()
        fb = ex._fallback_response("hard_braking", 0.5, 7.5)
        assert len(fb["explanation"]) > 0
        assert len(fb["recommendation"]) > 0
        assert len(fb["score_impact_text"]) > 0

    def test_explanation_result_dataclass(self) -> None:
        from scripts.genai import ExplanationResult
        r = ExplanationResult(
            anomaly_id="abc",
            explanation="Something happened.",
            recommendation="Drive carefully.",
            score_impact_text="Lost 10 points.",
        )
        assert r.anomaly_id == "abc"
        assert r.score_impact_text == "Lost 10 points."

"""
Claude API integration for anomaly explanation generation.

For each detected anomaly, calls the Claude API to generate:
  1. A 2–3 sentence natural language description of what happened
  2. A specific, actionable recommendation for the driver
  3. A plain-language explanation of how this affects their driving score

Responses are cached in the DB (anomalies.ai_explanation) so the API
is only called once per anomaly.

Model: claude-sonnet-4-6
"""

import json
import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Human-readable labels for anomaly types used in prompts
_ANOMALY_LABELS = {
    "hard_braking": "hard braking",
    "hard_acceleration": "hard acceleration",
    "near_miss": "near-miss / collision risk",
    "lane_departure": "lane departure",
    "traffic_violation": "traffic violation",
    "tailgating": "tailgating (unsafe following distance)",
    "aggressive_lane_change": "aggressive lane change",
    "harsh_cornering": "harsh cornering",
    "distracted_driving": "distracted driving",
    "other": "driving anomaly",
}

_SEVERITY_LABELS = {
    (0.0, 0.33): "minor",
    (0.33, 0.66): "moderate",
    (0.66, 1.01): "severe",
}


def _severity_label(severity: float) -> str:
    for (lo, hi), label in _SEVERITY_LABELS.items():
        if lo <= severity < hi:
            return label
    return "moderate"


@dataclass
class ExplanationResult:
    """Claude-generated explanation for a single anomaly event."""
    anomaly_id: str
    explanation: str          # What happened and why it matters
    recommendation: str       # Specific advice for the driver
    score_impact_text: str    # Plain-language score impact statement


class AnomalyExplainer:
    """
    Generates natural language explanations for detected anomalies
    using the Claude API.
    """

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 400

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the explainer.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        """
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                ) from exc
        return self._client

    def explain(
        self,
        anomaly_id: str,
        anomaly_type: str,
        severity: float,
        score_impact: float,
        detected_objects: list[str],
        timestamp_start: float,
        timestamp_end: float,
    ) -> ExplanationResult:
        """
        Generate a natural language explanation for a detected anomaly.

        Args:
            anomaly_id: UUID of the anomaly record.
            anomaly_type: Category string (e.g. "hard_braking").
            severity: Severity score 0.0–1.0.
            score_impact: Points deducted from the driving score.
            detected_objects: Objects detected in the anomaly window.
            timestamp_start: Start time (seconds) within the clip.
            timestamp_end: End time (seconds) within the clip.

        Returns:
            ExplanationResult with explanation, recommendation, and score text.
        """
        client = self._get_client()
        prompt = self._build_prompt(
            anomaly_type=anomaly_type,
            severity=severity,
            score_impact=score_impact,
            detected_objects=detected_objects,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
        )

        try:
            message = client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            parsed = self._parse_response(raw)
        except Exception as exc:
            logger.error("Claude API call failed for anomaly %s: %s", anomaly_id, exc)
            parsed = self._fallback_response(anomaly_type, severity, score_impact)

        return ExplanationResult(
            anomaly_id=anomaly_id,
            explanation=parsed["explanation"],
            recommendation=parsed["recommendation"],
            score_impact_text=parsed["score_impact_text"],
        )

    def explain_batch(self, anomalies: list[dict]) -> list[ExplanationResult]:
        """
        Generate explanations for a list of anomaly records.

        Calls explain() sequentially with a short delay to respect rate limits.

        Args:
            anomalies: List of dicts matching the explain() signature kwargs.

        Returns:
            List of ExplanationResult, one per anomaly.
        """
        results = []
        for i, anomaly in enumerate(anomalies):
            result = self.explain(**anomaly)
            results.append(result)
            logger.info(
                "Explained anomaly %d/%d: %s",
                i + 1, len(anomalies), anomaly.get("anomaly_id", "?"),
            )
            if i < len(anomalies) - 1:
                time.sleep(0.5)   # Avoid rate limit bursts
        return results

    def _build_prompt(
        self,
        anomaly_type: str,
        severity: float,
        score_impact: float,
        detected_objects: list[str],
        timestamp_start: float,
        timestamp_end: float,
    ) -> str:
        """
        Construct the Claude prompt for a given anomaly event.
        """
        label = _ANOMALY_LABELS.get(anomaly_type, "driving anomaly")
        sev_label = _severity_label(severity)
        duration = round(timestamp_end - timestamp_start, 1)
        objects_str = (
            ", ".join(detected_objects) if detected_objects else "no specific objects noted"
        )
        score_pts = round(score_impact, 1)

        return f"""You are a driving safety coach analyzing dashcam footage. A driving anomaly was detected and you need to provide a clear, concise explanation for the driver.

Anomaly details:
- Type: {label}
- Severity: {sev_label} ({severity:.0%})
- Duration: {duration} seconds (from {timestamp_start:.1f}s to {timestamp_end:.1f}s in the clip)
- Objects detected nearby: {objects_str}
- Score impact: -{score_pts} points from the driving score

Respond with ONLY a JSON object in this exact format (no extra text):
{{
  "explanation": "2-3 sentences describing what happened and why it is a safety concern. Be specific and factual based on the anomaly type and severity.",
  "recommendation": "One specific, actionable piece of advice the driver can follow to avoid this in the future.",
  "score_impact_text": "One sentence explaining the score impact in plain language (e.g. 'This {sev_label} {label} cost you {score_pts} points from your driving score.')."
}}"""

    def _parse_response(self, raw: str) -> dict:
        """
        Parse Claude's JSON response.

        Falls back to splitting on newlines if JSON parsing fails.
        """
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            data = json.loads(raw)
            return {
                "explanation": data.get("explanation", ""),
                "recommendation": data.get("recommendation", ""),
                "score_impact_text": data.get("score_impact_text", ""),
            }
        except json.JSONDecodeError:
            logger.warning("Failed to parse Claude response as JSON, using raw text")
            return {
                "explanation": raw[:300] if raw else "An anomaly was detected.",
                "recommendation": "Review your driving habits for this type of event.",
                "score_impact_text": "This event affected your driving score.",
            }

    def _fallback_response(
        self, anomaly_type: str, severity: float, score_impact: float
    ) -> dict:
        """Generate a rule-based fallback when the API call fails."""
        label = _ANOMALY_LABELS.get(anomaly_type, "driving anomaly")
        sev_label = _severity_label(severity)
        score_pts = round(score_impact, 1)
        return {
            "explanation": (
                f"A {sev_label} {label} was detected in your dashcam footage. "
                f"This type of event can increase collision risk and is flagged "
                f"by the safety system for review."
            ),
            "recommendation": (
                f"Review your dashcam footage of this event and consider how to "
                f"avoid similar {label} situations in the future."
            ),
            "score_impact_text": (
                f"This {sev_label} {label} deducted {score_pts} points from your driving score."
            ),
        }

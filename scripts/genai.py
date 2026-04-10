"""
Claude API integration for anomaly explanation generation.

For each detected anomaly, calls the Claude API to generate:
  1. A 2–3 sentence natural language description of what happened
  2. A specific, actionable recommendation for the driver
  3. A plain-language explanation of how this affects their driving score

Responses are cached in the DB (anomalies.ai_explanation) so the API
is only called once per anomaly.

Implemented in: feature/scoring-genai

Model: claude-sonnet-4-6
"""

from dataclasses import dataclass


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

    Implemented in feature/scoring-genai.
    """

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 300

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the explainer with an Anthropic API key.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        """
        self._api_key = api_key
        self._client = None  # anthropic.Anthropic initialized on first use

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
            anomaly_type: Category of the anomaly (e.g., "hard_braking").
            severity: Severity score 0.0–1.0.
            score_impact: Points deducted from the driving score.
            detected_objects: List of objects detected in the anomaly window.
            timestamp_start: Start time (seconds) within the clip.
            timestamp_end: End time (seconds) within the clip.

        Returns:
            ExplanationResult with explanation, recommendation, and score text.
        """
        raise NotImplementedError("Implemented in feature/scoring-genai")

    def explain_batch(self, anomalies: list[dict]) -> list[ExplanationResult]:
        """
        Generate explanations for a list of anomaly records.

        Calls explain() sequentially with a small delay to respect rate limits.

        Args:
            anomalies: List of dicts matching the explain() signature kwargs.

        Returns:
            List of ExplanationResult, one per anomaly.
        """
        raise NotImplementedError("Implemented in feature/scoring-genai")

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

        Implemented in feature/scoring-genai.
        """
        raise NotImplementedError("Implemented in feature/scoring-genai")

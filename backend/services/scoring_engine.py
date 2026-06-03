"""
P.R.I.S.M. — Deterministic Scoring Engine
===========================================
Computes the integrity score from detection outputs WITHOUT any GPT/API calls.
This engine ALWAYS runs — GPT only explains the pre-computed score.

Sub-scores (each 0.0-10.0):
  - boundary_score:   Based on HIGH/MEDIUM confidence boundary count
  - coherence_score:  From topic coherence analysis (% coherent transitions)
  - citation_score:   Temporal anomalies (0 weight if no citations)
  - burstiness_score: Mean burstiness coefficient (soft, no threshold)

Final integrity = weighted average of active sub-scores.
Verdict: Clean (8-10) / Suspicious (5-7.9) / Flagged (2-4.9) / Critical (0-1.9)
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    CLEAN = "Clean"
    SUSPICIOUS = "Suspicious"
    FLAGGED = "Flagged"
    CRITICAL = "Critical"


# ─── Default Weights ─────────────────────────────────────────────────────────
# Equal weights initially. Validated qualitatively: genuine > 8, stitched < 4.
# NOT optimized via grid search (no ground-truth scores exist).
DEFAULT_WEIGHTS = {
    "boundary": 1.0,
    "coherence": 1.0,
    "citation": 1.0,   # Set to 0.0 automatically if no citations found
    "burstiness": 0.3,  # Lower weight — contested signal
}


class ScoringEngine:
    """
    Deterministic scoring from detection outputs. No GPT dependency.
    This is the single source of truth for the integrity score.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def score(
        self,
        boundary_result: Dict[str, Any],
        coherence_result: Optional[Dict[str, Any]] = None,
        citation_result: Optional[Dict[str, Any]] = None,
        burstiness_values: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Compute the integrity score from all evidence streams.

        Args:
            boundary_result: Output from BoundaryFusion.fuse() or clustering result
            coherence_result: Output from TopicCoherenceAnalyzer.analyze()
            citation_result: Output from citation forensics
            burstiness_values: List of burstiness coefficients per paragraph

        Returns:
            Dict with integrity_score, verdict, sub_scores, and breakdown.
        """
        sub_scores = {}
        active_weights = {}

        # ── 1. Boundary sub-score ────────────────────────────────────────────
        sub_scores["boundary"] = self._compute_boundary_score(boundary_result)
        active_weights["boundary"] = self.weights["boundary"]

        # ── 2. Coherence sub-score ───────────────────────────────────────────
        if coherence_result and coherence_result.get("coherence_score") is not None:
            sub_scores["coherence"] = coherence_result["coherence_score"]
            active_weights["coherence"] = self.weights["coherence"]
        else:
            sub_scores["coherence"] = 10.0
            active_weights["coherence"] = self.weights["coherence"]

        # ── 3. Citation sub-score ────────────────────────────────────────────
        citation_score, has_citations = self._compute_citation_score(citation_result)
        sub_scores["citation"] = citation_score
        # Zero weight if no citations found (can't penalize for missing data)
        active_weights["citation"] = self.weights["citation"] if has_citations else 0.0

        # ── 4. Burstiness sub-score ──────────────────────────────────────────
        sub_scores["burstiness"] = self._compute_burstiness_score(burstiness_values)
        active_weights["burstiness"] = self.weights["burstiness"]

        # ── Final weighted average ───────────────────────────────────────────
        total_weight = sum(active_weights.values())
        if total_weight > 0:
            integrity_score = sum(
                sub_scores[k] * active_weights[k] for k in sub_scores
            ) / total_weight
        else:
            integrity_score = 10.0

        integrity_score = round(max(0.0, min(10.0, integrity_score)), 1)

        # ── Verdict ──────────────────────────────────────────────────────────
        verdict = self._score_to_verdict(integrity_score)

        result = {
            "integrity_score": integrity_score,
            "verdict": verdict.value,
            "sub_scores": {k: round(v, 2) for k, v in sub_scores.items()},
            "weights": active_weights,
            "total_weight": round(total_weight, 2),
        }

        logger.info(
            f"[P.R.I.S.M.] Scoring: {integrity_score}/10 -> {verdict.value} "
            f"(boundary={sub_scores['boundary']:.1f}, "
            f"coherence={sub_scores['coherence']:.1f}, "
            f"citation={sub_scores['citation']:.1f}, "
            f"burstiness={sub_scores['burstiness']:.1f})"
        )

        return result

    # ─── Sub-score Computations ──────────────────────────────────────────────

    @staticmethod
    def _compute_boundary_score(boundary_result: Dict[str, Any]) -> float:
        """
        Higher boundaries = lower score.
        HIGH confidence boundaries penalized more than MEDIUM.
        """
        high = boundary_result.get("high_confidence_count", 0)
        medium = boundary_result.get("medium_confidence_count", 0)
        total = boundary_result.get("total_boundaries",
                                     boundary_result.get("boundary_count", 0))

        if total == 0:
            return 10.0  # No boundaries = clean

        # Each HIGH boundary = -3.0, each MEDIUM = -1.5, capped at 0
        penalty = high * 3.0 + medium * 1.5
        return max(0.0, 10.0 - penalty)

    @staticmethod
    def _compute_citation_score(citation_result: Optional[Dict[str, Any]]) -> tuple:
        """
        Returns (score, has_citations).
        If no citations found, returns (10.0, False) — zero weight applied upstream.
        """
        if not citation_result or not isinstance(citation_result, dict):
            return 10.0, False

        total_citations = citation_result.get("total_citations_found", 0)
        if total_citations == 0:
            return 10.0, False

        anomalies = citation_result.get("temporal_anomalies", [])
        if not anomalies:
            return 10.0, True

        # Penalize by anomaly severity
        penalty = 0.0
        for a in anomalies:
            severity = a.get("severity", "low")
            if severity == "high":
                penalty += 3.0
            elif severity == "medium":
                penalty += 1.5
            else:
                penalty += 0.5

        return max(0.0, 10.0 - penalty), True

    @staticmethod
    def _compute_burstiness_score(burstiness_values: Optional[List[float]]) -> float:
        """
        Burstiness as a soft signal. Very low burstiness is suspicious
        (possible AI generation) but NOT conclusive.
        """
        if not burstiness_values or len(burstiness_values) < 2:
            return 10.0  # Not enough data to assess

        avg = float(sum(burstiness_values) / len(burstiness_values))

        # Normal human burstiness is ~0.3-1.0+
        # Very low (<0.15) is suspicious, but we score gently
        if avg >= 0.4:
            return 10.0
        elif avg >= 0.25:
            return 7.0
        elif avg >= 0.15:
            return 4.0
        else:
            return 2.0

    @staticmethod
    def _score_to_verdict(score: float) -> Verdict:
        """Map integrity score to 4-tier verdict."""
        if score >= 8.0:
            return Verdict.CLEAN
        elif score >= 5.0:
            return Verdict.SUSPICIOUS
        elif score >= 2.0:
            return Verdict.FLAGGED
        else:
            return Verdict.CRITICAL

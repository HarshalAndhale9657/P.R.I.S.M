"""
P.R.I.S.M. — Topic Coherence Analyzer
=======================================
Measures semantic coherence between adjacent paragraphs using MiniLM embeddings.
Flags transitions where similarity drops significantly (> mean - 2*sigma).

This is an independent evidence stream — it does NOT affect clustering,
but contributes to the overall integrity score via the scoring engine.

Key insight: when a stitched paragraph is inserted, the topic coherence
between it and its neighbors drops sharply, even if stylometric features
are similar (e.g., when the plagiarist mimics the writing style but
changes the topic).
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class TopicCoherenceAnalyzer:
    """
    Analyzes topic coherence between adjacent paragraphs.
    Uses local MiniLM embeddings (no API calls).
    """

    def __init__(self, sigma_threshold: float = 2.0):
        """
        Args:
            sigma_threshold: Flag transitions where similarity < mean - sigma_threshold * std.
                            Higher = less sensitive, Lower = more flags.
        """
        self.sigma_threshold = sigma_threshold
        self._embedding_service = None

    def _get_embeddings(self):
        """Lazy-load the shared embedding service."""
        if self._embedding_service is None:
            try:
                from services.local_embeddings import get_instance
                self._embedding_service = get_instance()
            except Exception as e:
                logger.error(f"[P.R.I.S.M.] Cannot load embedding service: {e}")
                raise
        return self._embedding_service

    def analyze(self, paragraphs: List[str]) -> Dict[str, Any]:
        """
        Analyze topic coherence between adjacent paragraphs.

        Args:
            paragraphs: List of paragraph text strings.

        Returns:
            Dict with:
                - similarities: list of adjacent-pair cosine similarities
                - flagged_transitions: indices where coherence drops sharply
                - coherence_score: sub-score for the scoring engine (0-10)
                - mean_similarity: average adjacent similarity
                - threshold: the computed threshold value
        """
        if len(paragraphs) < 2:
            return self._single_paragraph_result()

        try:
            service = self._get_embeddings()
            similarities = service.pairwise_similarity(paragraphs)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Topic coherence analysis failed: {e}")
            return self._fallback_result(len(paragraphs))

        if not similarities:
            return self._single_paragraph_result()

        mean_sim = float(np.mean(similarities))
        std_sim = float(np.std(similarities))

        # Threshold: flag transitions below mean - sigma_threshold * std
        threshold = mean_sim - self.sigma_threshold * std_sim

        flagged = []
        for i, sim in enumerate(similarities):
            if sim < threshold:
                flagged.append({
                    "between_paragraphs": [i, i + 1],
                    "similarity": round(sim, 4),
                    "threshold": round(threshold, 4),
                    "deviation": round((mean_sim - sim) / max(std_sim, 1e-10), 2),
                })

        # Coherence sub-score: 10 * (coherent transitions / total transitions)
        coherent_count = len(similarities) - len(flagged)
        coherence_score = 10.0 * coherent_count / max(len(similarities), 1)

        logger.info(
            f"[P.R.I.S.M.] Topic coherence: {len(flagged)} flagged transitions "
            f"out of {len(similarities)} (score: {coherence_score:.1f}/10, "
            f"mean sim: {mean_sim:.3f}, threshold: {threshold:.3f})"
        )

        return {
            "similarities": [round(s, 4) for s in similarities],
            "flagged_transitions": flagged,
            "flagged_count": len(flagged),
            "total_transitions": len(similarities),
            "coherence_score": round(coherence_score, 2),
            "mean_similarity": round(mean_sim, 4),
            "std_similarity": round(std_sim, 4),
            "threshold": round(threshold, 4),
        }

    @staticmethod
    def _single_paragraph_result() -> Dict[str, Any]:
        return {
            "similarities": [],
            "flagged_transitions": [],
            "flagged_count": 0,
            "total_transitions": 0,
            "coherence_score": 10.0,
            "mean_similarity": 1.0,
            "std_similarity": 0.0,
            "threshold": 0.0,
        }

    @staticmethod
    def _fallback_result(n_paragraphs: int) -> Dict[str, Any]:
        """Return neutral result when embedding service is unavailable."""
        return {
            "similarities": [],
            "flagged_transitions": [],
            "flagged_count": 0,
            "total_transitions": max(n_paragraphs - 1, 0),
            "coherence_score": 10.0,
            "mean_similarity": None,
            "std_similarity": None,
            "threshold": None,
            "error": "Embedding service unavailable",
        }

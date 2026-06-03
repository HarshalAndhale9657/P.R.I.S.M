"""
P.R.I.S.M. — Embedding Similarity Detector
=============================================
Detects style/author change boundaries by measuring cosine similarity drops
between consecutive paragraph embeddings using the local MiniLM model.

This mimics the core strategy of PAN 2023 winning systems (paragraph-pair
comparison via transformers) but uses our existing offline MiniLM service
instead of a fine-tuned DeBERTa.

Pipeline: Paragraphs → MiniLM embeddings → Cosine similarity curve → Boundary detection
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class EmbeddingSimilarityDetector:
    """
    Detects author-change boundaries by finding drops in cosine similarity
    between consecutive paragraph embeddings.

    Unlike stylometric features (which describe each paragraph independently),
    this captures *relational* information: how similar adjacent paragraphs
    are to each other. A sharp drop in similarity suggests a different author.
    """

    def __init__(self, sigma: float = 1.0, min_similarity_drop: float = 0.05):
        """
        Args:
            sigma: Number of standard deviations below mean similarity to
                   flag as a boundary. Lower = more boundaries detected.
            min_similarity_drop: Minimum absolute similarity drop to consider.
                                Prevents noisy detections in uniform documents.
        """
        self.sigma = sigma
        self.min_similarity_drop = min_similarity_drop
        self._embedding_service = None

    def _get_embedding_service(self):
        """Lazy-load the embedding service."""
        if self._embedding_service is None:
            from services.local_embeddings import get_instance
            self._embedding_service = get_instance()
        return self._embedding_service

    def detect(self, paragraphs: List[str]) -> Dict[str, Any]:
        """
        Detect boundaries from embedding similarity drops.

        Args:
            paragraphs: List of paragraph text strings.

        Returns:
            Dict with:
                - boundaries: List of paragraph indices where style changes
                - similarities: List of cosine similarities between adjacent pairs
                - threshold: The adaptive threshold used
                - method: "embedding_similarity"
        """
        if len(paragraphs) < 2:
            return self._empty_result()

        try:
            service = self._get_embedding_service()
            similarities = service.pairwise_similarity(paragraphs)
        except Exception as e:
            logger.warning(f"[P.R.I.S.M.] Embedding similarity failed: {e}")
            return self._empty_result()

        if not similarities or len(similarities) == 0:
            return self._empty_result()

        sim_array = np.array(similarities)
        mean_sim = np.mean(sim_array)
        std_sim = np.std(sim_array)

        # Adaptive threshold: mean - sigma * std
        # But never above (mean - min_drop) to ensure some sensitivity
        threshold = min(
            mean_sim - self.sigma * std_sim,
            mean_sim - self.min_similarity_drop
        )

        # Detect boundaries where similarity drops below threshold
        boundaries = []
        for i, sim in enumerate(similarities):
            if sim < threshold:
                # Boundary is AFTER paragraph i (between paragraph i and i+1)
                boundaries.append(i + 1)

        logger.debug(
            f"[EmbeddingSim] {len(boundaries)} boundaries detected "
            f"(threshold={threshold:.3f}, mean_sim={mean_sim:.3f})"
        )

        return {
            "boundaries": boundaries,
            "similarities": similarities,
            "threshold": float(threshold),
            "mean_similarity": float(mean_sim),
            "std_similarity": float(std_sim),
            "method": "embedding_similarity",
        }

    def get_similarity_features(self, paragraphs: List[str]) -> np.ndarray:
        """
        Extract embedding-derived features for each paragraph position.
        Returns an (N, 3) array with:
            - sim_prev: cosine similarity with previous paragraph (0 for first)
            - sim_next: cosine similarity with next paragraph (0 for last)
            - sim_drop: |sim_prev - sim_next| (0 for first/last)

        These can be appended to the stylometric feature matrix to give
        PELT/Distance access to relational signals.
        """
        n = len(paragraphs)
        features = np.zeros((n, 3))

        if n < 2:
            return features

        try:
            service = self._get_embedding_service()
            similarities = service.pairwise_similarity(paragraphs)
        except Exception:
            return features

        for i in range(n):
            # sim_prev
            if i > 0:
                features[i, 0] = similarities[i - 1]
            # sim_next
            if i < n - 1:
                features[i, 1] = similarities[i]
            # sim_drop
            if 0 < i < n - 1:
                features[i, 2] = abs(similarities[i - 1] - similarities[i])

        return features

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "boundaries": [],
            "similarities": [],
            "threshold": 0.0,
            "mean_similarity": 0.0,
            "std_similarity": 0.0,
            "method": "embedding_similarity",
        }

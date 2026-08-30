"""
P.R.I.S.M. — Local Embedding Service
======================================
Shared MiniLM embedding service used by both topic_coherence and source_tracer.
Prevents loading the ~90MB model twice.

Uses sentence-transformers' paraphrase-multilingual-MiniLM-L12-v2 (384 dims).
Fully offline — no API calls required.
"""

import logging
import threading
import numpy as np
from typing import List, Optional
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

_INSTANCE: Optional["LocalEmbeddingService"] = None
_INSTANCE_LOCK = threading.Lock()


class LocalEmbeddingService:
    """
    Singleton embedding service using MiniLM.
    Call get_instance() to reuse the same model across modules.
    """

    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM = 384

    def __init__(self):
        self._model = None
        self._load_lock = threading.Lock()

    def _load_model(self):
        """Lazy-load the model on first use (thread-safe, double-checked)."""
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"[P.R.I.S.M.] Loading {self.MODEL_NAME}...")
                self._model = SentenceTransformer(self.MODEL_NAME)
                logger.info(f"[P.R.I.S.M.] {self.MODEL_NAME} loaded ({self.EMBEDDING_DIM} dims)")
            except ImportError:
                logger.error(
                    "[P.R.I.S.M.] sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"[P.R.I.S.M.] Failed to load embedding model: {e}")
                raise

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Compute embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            np.ndarray of shape (len(texts), 384)
        """
        self._load_model()
        return self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

    def pairwise_similarity(self, texts: List[str]) -> List[float]:
        """
        Compute cosine similarity between each pair of adjacent texts.

        Args:
            texts: List of N text strings.

        Returns:
            List of N-1 similarity scores between adjacent pairs.
        """
        if len(texts) < 2:
            return []

        embeddings = self.embed(texts)
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = cosine_similarity(
                embeddings[i].reshape(1, -1),
                embeddings[i + 1].reshape(1, -1)
            )[0][0]
            similarities.append(float(sim))

        return similarities

    def similarity_matrix(self, texts: List[str]) -> np.ndarray:
        """
        Compute full NxN cosine similarity matrix.

        Args:
            texts: List of N text strings.

        Returns:
            np.ndarray of shape (N, N) with pairwise cosine similarities.
        """
        embeddings = self.embed(texts)
        return cosine_similarity(embeddings)


def get_instance() -> LocalEmbeddingService:
    """Get the singleton embedding service instance (thread-safe)."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = LocalEmbeddingService()
    return _INSTANCE

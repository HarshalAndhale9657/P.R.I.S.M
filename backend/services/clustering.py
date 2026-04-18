"""
P.R.I.S.M. — HDBSCAN Authorship Clustering Engine

Density-based clustering to automatically detect the number of distinct
authors in a document WITHOUT specifying K (number of clusters).

Key advantages over K-Means:
  - Auto-determines cluster count from data density
  - Cluster -1 = noise = stylistically anomalous = likely stitched
  - No spherical cluster assumption
  - Robust to varying cluster sizes

Pipeline: Feature Matrix → StandardScaler → HDBSCAN → Cluster Labels
"""

import logging
import numpy as np
import hdbscan
from sklearn.preprocessing import StandardScaler
from typing import List, Dict, Any, Optional

from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)


class AuthorshipClustering:
    """
    Clusters paragraphs by writing style using HDBSCAN density-based clustering.
    Paragraphs assigned to Cluster -1 are flagged as stylistic anomalies
    (high probability of being stitched from a different source).
    """

    def __init__(self, min_cluster_size: int = 3, min_samples: int = 2):
        """
        Args:
            min_cluster_size: Minimum paragraphs to form a distinct authorial cluster.
                              Lower = more sensitive, Higher = fewer false positives.
            min_samples: Core point threshold. Controls how conservative the
                         clustering is. Lower = more clusters, Higher = stricter.
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.scaler = StandardScaler()

    def cluster(
        self,
        feature_matrix: np.ndarray,
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        """
        Run the full clustering pipeline on a feature matrix.

        Args:
            feature_matrix: np.ndarray of shape (N, 7) — one row per paragraph.
            ctx: Optional PipelineContext for warning accumulation.

        Returns:
            Dict containing:
                - clusters: list of cluster IDs per paragraph (-1 = anomaly)
                - estimated_authors: number of distinct author clusters
                - anomaly_indices: indices of Cluster -1 paragraphs
                - boundaries: indices where cluster transitions occur
                - noise_percentage: fraction of paragraphs flagged as noise
                - cluster_sizes: dict mapping cluster_id → paragraph count
                - confidence: float 0-1 indicating clustering reliability
        """
        if ctx is None:
            ctx = PipelineContext()

        n_paragraphs = len(feature_matrix)

        # ── Edge Case: Upstream signaled skip ────────────────────────────────
        if ctx.skip_clustering:
            logger.info("[P.R.I.S.M.] Clustering skipped (upstream signal).")
            ctx.add_warning(
                WarningCode.CLUSTER_SKIPPED_SHORT, WarningSeverity.WARNING, "clustering",
                f"Clustering skipped — document has too few paragraphs for reliable analysis.",
                {"paragraph_count": n_paragraphs},
            )
            return self._single_author_result(n_paragraphs, too_short=True)

        # ── Edge Case: Too few paragraphs for clustering ─────────────────────
        if n_paragraphs < self.min_cluster_size * 2:
            logger.warning(
                f"[P.R.I.S.M.] Only {n_paragraphs} paragraphs — "
                f"too few for reliable clustering (need >= {self.min_cluster_size * 2}). "
                f"Assigning all to Cluster 0."
            )
            ctx.add_warning(
                WarningCode.CLUSTER_SKIPPED_SHORT, WarningSeverity.WARNING, "clustering",
                f"Only {n_paragraphs} paragraphs — need at least {self.min_cluster_size * 2} "
                f"for density-based clustering. All paragraphs assigned to a single author.",
                {"paragraph_count": n_paragraphs, "minimum_required": self.min_cluster_size * 2},
            )
            return self._single_author_result(n_paragraphs, too_short=True)

        # ── Edge Case: Zero-variance features ────────────────────────────────
        # If all paragraphs have identical features, StandardScaler produces
        # NaN/Inf, and HDBSCAN crashes. Detect and bypass.
        column_variances = np.var(feature_matrix, axis=0)
        if np.all(column_variances < 1e-10):
            logger.warning(
                "[P.R.I.S.M.] All paragraphs have identical stylometric features. "
                "Bypassing clustering — single author detected."
            )
            ctx.add_warning(
                WarningCode.CLUSTER_ZERO_VARIANCE, WarningSeverity.INFO, "clustering",
                "All paragraphs have virtually identical stylometric features. "
                "This indicates consistent writing style throughout — single author detected.",
            )
            return self._single_author_result(n_paragraphs)

        # ── Remove zero-variance columns before scaling ──────────────────────
        # StandardScaler divides by std — zero std = division by zero = NaN
        valid_columns = column_variances >= 1e-10
        filtered_matrix = feature_matrix[:, valid_columns]

        if filtered_matrix.shape[1] < 2:
            logger.warning(
                "[P.R.I.S.M.] Too few variable features for meaningful clustering."
            )
            ctx.add_warning(
                WarningCode.CLUSTER_ZERO_VARIANCE, WarningSeverity.WARNING, "clustering",
                "Too few variable features for meaningful clustering — "
                "most stylometric dimensions are constant across paragraphs.",
                {"variable_features": int(filtered_matrix.shape[1])},
            )
            return self._single_author_result(n_paragraphs)

        # ── Scale features to zero mean, unit variance ───────────────────────
        # Critical: Euclidean distance is sensitive to feature scale.
        # Yule's K can be ~200 while pronoun_ratio is ~0.05
        try:
            scaled_features = self.scaler.fit_transform(filtered_matrix)
            # Prevent OpenAI semantics from over-fragmenting topics
            # Down-weight indices 8,9,10 (semantic) relative to structural features
            if scaled_features.shape[1] >= 11:
                scaled_features[:, 8:11] *= 0.20
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Feature scaling failed: {e}")
            return self._single_author_result(n_paragraphs)

        # ── Run HDBSCAN ──────────────────────────────────────────────────────
        try:
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric="euclidean",
                cluster_selection_method="eom",  # Excess of Mass — most stable
            )
            labels = clusterer.fit_predict(scaled_features)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] HDBSCAN clustering failed: {e}")
            return self._single_author_result(n_paragraphs)

        # ── Edge Case: Noise Saturation ──────────────────────────────────────
        # If >80% of paragraphs are noise (-1), HDBSCAN failed to find
        # meaningful structure. Override to single author.
        noise_count = int(np.sum(labels == -1))
        noise_pct = noise_count / n_paragraphs

        if noise_pct > 0.90:
            logger.warning(
                f"[P.R.I.S.M.] {noise_pct:.0%} of paragraphs are noise — "
                f"HDBSCAN saturation detected. Overriding to single author."
            )
            ctx.add_warning(
                WarningCode.CLUSTER_NOISE_OVERRIDE, WarningSeverity.WARNING, "clustering",
                f"{noise_pct:.0%} of paragraphs were classified as noise, indicating "
                f"HDBSCAN could not find meaningful clusters. All paragraphs have been "
                f"assigned to a single author group.",
                {"noise_percentage": round(noise_pct, 4)},
            )
            return self._single_author_result(n_paragraphs, noise_override=True)

        # ── Build result ─────────────────────────────────────────────────────
        cluster_labels = labels.tolist()
        unique_clusters = set(cluster_labels)
        author_clusters = [c for c in unique_clusters if c != -1]

        # Find boundaries — positions where cluster ID changes
        boundaries = []
        for i in range(1, len(cluster_labels)):
            if cluster_labels[i] != cluster_labels[i - 1]:
                boundaries.append({
                    "after_paragraph": i - 1,
                    "from_cluster": cluster_labels[i - 1],
                    "to_cluster": cluster_labels[i],
                    "is_anomaly_transition": (
                        cluster_labels[i] == -1 or cluster_labels[i - 1] == -1
                    ),
                })

        # Cluster sizes
        cluster_sizes = {}
        for c in unique_clusters:
            cluster_sizes[str(c)] = cluster_labels.count(c)

        # Confidence score — based on cluster stability
        confidence = self._calculate_confidence(
            clusterer, labels, noise_pct, len(author_clusters)
        )

        # Single-author informational warning
        if len(author_clusters) == 1 and noise_count == 0:
            ctx.add_warning(
                WarningCode.CLUSTER_SINGLE_AUTHOR, WarningSeverity.INFO, "clustering",
                "All paragraphs belong to a single authorial cluster — "
                "no stylistic anomalies detected.",
            )

        result = {
            "clusters": cluster_labels,
            "estimated_authors": len(author_clusters),
            "anomaly_indices": [i for i, l in enumerate(cluster_labels) if l == -1],
            "anomaly_count": noise_count,
            "boundaries": boundaries,
            "boundary_count": len(boundaries),
            "noise_percentage": round(noise_pct, 4),
            "cluster_sizes": cluster_sizes,
            "confidence": round(confidence, 4),
            "noise_override": False,
            "too_short": False,
        }

        logger.info(
            f"[P.R.I.S.M.] Clustering complete: "
            f"{result['estimated_authors']} authors detected, "
            f"{noise_count} anomalies flagged, "
            f"{len(boundaries)} boundaries found, "
            f"confidence: {confidence:.2f}"
        )

        return result

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _single_author_result(
        self, n_paragraphs: int, noise_override: bool = False, too_short: bool = False,
    ) -> Dict[str, Any]:
        """Return a clean single-author result (no anomalies)."""
        return {
            "clusters": [0] * n_paragraphs,
            "estimated_authors": 1,
            "anomaly_indices": [],
            "anomaly_count": 0,
            "boundaries": [],
            "boundary_count": 0,
            "noise_percentage": 0.0,
            "cluster_sizes": {"0": n_paragraphs},
            "confidence": 1.0 if not noise_override else 0.3,
            "noise_override": noise_override,
            "too_short": too_short or n_paragraphs < self.min_cluster_size * 2,
        }

    def _calculate_confidence(
        self,
        clusterer: hdbscan.HDBSCAN,
        labels: np.ndarray,
        noise_pct: float,
        n_clusters: int,
    ) -> float:
        """
        Calculate a confidence score for the clustering result.

        Factors:
        - HDBSCAN probabilities (how confident each point assignment is)
        - Noise percentage (high noise = less confidence)
        - Number of clusters found (reasonable range = higher confidence)
        """
        # Base: average HDBSCAN membership probability (excluding noise)
        non_noise_mask = labels != -1
        if np.any(non_noise_mask) and hasattr(clusterer, "probabilities_"):
            avg_probability = float(np.mean(clusterer.probabilities_[non_noise_mask]))
        else:
            avg_probability = 0.5

        # Penalty for high noise
        noise_penalty = max(0, 1.0 - noise_pct * 2)

        # Bonus for reasonable cluster count (1-5 authors is expected)
        cluster_bonus = 1.0 if 1 <= n_clusters <= 5 else 0.7

        confidence = avg_probability * noise_penalty * cluster_bonus
        return max(0.1, min(1.0, confidence))

    def get_cluster_summary(
        self, paragraphs: List[Dict], cluster_result: Dict
    ) -> List[Dict]:
        """
        Enrich paragraphs with cluster information for frontend rendering.

        Args:
            paragraphs: Original paragraph dicts from PDF parser.
            cluster_result: Output from self.cluster().

        Returns:
            Enriched paragraph dicts with cluster_id, is_anomaly, etc.
        """
        clusters = cluster_result["clusters"]
        enriched = []

        for i, para in enumerate(paragraphs):
            cluster_id = clusters[i] if i < len(clusters) else 0
            enriched.append({
                **para,
                "cluster_id": cluster_id,
                "is_anomaly": cluster_id == -1,
                "cluster_label": (
                    "ANOMALY" if cluster_id == -1
                    else f"Author {cluster_id + 1}"
                ),
            })

        return enriched

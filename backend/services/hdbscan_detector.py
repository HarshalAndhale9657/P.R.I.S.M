"""
P.R.I.S.M. — HDBSCAN Authorship Clustering
============================================
Detects stylometric discontinuities in academic text using HDBSCAN
density clustering over a normalised N×27 feature matrix.

Patch notes (v3.1):
  - StandardScaler is now instantiated per cluster() call — thread-safe,
    no shared mutable state between concurrent requests.
  - Adaptive variance-based down-weighting applied before scaling: features
    with near-zero variance across the document are attenuated so that
    degenerate dimensions don't dominate the Euclidean distance metric.
"""

import logging
import numpy as np
from sklearn.preprocessing import StandardScaler
from typing import List, Dict, Any, Optional

try:
    import hdbscan
except ImportError:
    hdbscan = None

from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

_VARIANCE_FLOOR = 1e-6
_DOWNWEIGHT_THRESHOLD = 0.01


class AuthorshipClustering:
    def __init__(self, min_cluster_size: int = 2, min_samples: int = 2):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples

    # ─── Public API ──────────────────────────────────────────────────────────

    def cluster(
        self,
        feature_matrix: np.ndarray,
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        if ctx is None:
            ctx = PipelineContext()

        n_paragraphs, n_features = feature_matrix.shape if feature_matrix.ndim == 2 else (0, 0)

        empty_result = self._empty_result(n_paragraphs)

        if n_paragraphs < 2:
            ctx.skip_clustering = True
            return empty_result

        if ctx.skip_clustering:
            return empty_result

        if hdbscan is None:
            ctx.add_warning(
                WarningCode.CLUSTER_HDBSCAN_UNAVAILABLE, WarningSeverity.ERROR, "hdbscan_detector",
                "hdbscan package is not installed — clustering skipped.",
            )
            ctx.skip_clustering = True
            return empty_result

        # ── Per-request scaler — never shared between threads ────────────────
        scaler = StandardScaler()

        # ── Adaptive down-weighting based on per-feature variance ────────────
        col_variances = np.var(feature_matrix, axis=0)
        weight_vector = np.where(
            col_variances < _DOWNWEIGHT_THRESHOLD,
            np.sqrt(np.maximum(col_variances, _VARIANCE_FLOOR) / _DOWNWEIGHT_THRESHOLD),
            1.0,
        )

        weighted_matrix = feature_matrix * weight_vector

        try:
            scaled = scaler.fit_transform(weighted_matrix)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Scaling failed: {e}")
            ctx.add_warning(
                WarningCode.CLUSTER_SCALING_FAILED, WarningSeverity.WARNING, "hdbscan_detector",
                f"Feature scaling failed: {str(e)[:200]}",
            )
            return empty_result

        try:
            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=max(self.min_cluster_size, 2),
                min_samples=self.min_samples,
                metric="euclidean",
                cluster_selection_method="eom",
                prediction_data=True,
            )
            labels = clusterer.fit_predict(scaled)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] HDBSCAN fit failed: {e}")
            ctx.add_warning(
                WarningCode.CLUSTER_FIT_FAILED, WarningSeverity.ERROR, "hdbscan_detector",
                f"HDBSCAN clustering failed: {str(e)[:200]}",
            )
            return empty_result

        return self._build_result(labels, n_paragraphs)

    def get_cluster_summary(
        self,
        paragraphs: List[Dict[str, Any]],
        cluster_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        clusters = cluster_result.get("clusters", [-1] * len(paragraphs))
        anomaly_indices = set(cluster_result.get("anomaly_indices", []))
        boundaries = set(cluster_result.get("boundaries", []))

        enriched = []
        for i, para in enumerate(paragraphs):
            enriched.append({
                **para,
                "cluster_id": clusters[i] if i < len(clusters) else -1,
                "is_anomaly": i in anomaly_indices,
                "is_boundary": i in boundaries,
            })
        return enriched

    # ─── Private ─────────────────────────────────────────────────────────────

    def _build_result(self, labels: np.ndarray, n_paragraphs: int) -> Dict[str, Any]:
        unique_labels = sorted(set(labels))
        real_clusters = [l for l in unique_labels if l >= 0]
        noise_mask = labels == -1

        anomaly_indices = [i for i, l in enumerate(labels) if l == -1]
        cluster_sizes = {str(cl): int(np.sum(labels == cl)) for cl in real_clusters}

        boundaries = []
        for i in range(1, n_paragraphs):
            if labels[i] != labels[i - 1]:
                boundaries.append(i)

        noise_pct = round(float(np.sum(noise_mask) / max(n_paragraphs, 1)) * 100, 2)
        estimated_authors = max(len(real_clusters), 1)
        noise_override = noise_pct > 60.0

        if len(real_clusters) == 0:
            confidence = "low"
        elif noise_pct < 15.0 and len(real_clusters) >= 2:
            confidence = "high"
        elif noise_pct < 35.0:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "clusters": labels.tolist(),
            "estimated_authors": estimated_authors,
            "anomaly_indices": anomaly_indices,
            "anomaly_count": len(anomaly_indices),
            "boundaries": boundaries,
            "boundary_count": len(boundaries),
            "noise_percentage": noise_pct,
            "cluster_sizes": cluster_sizes,
            "confidence": confidence,
            "noise_override": noise_override,
            "too_short": False,
        }

    @staticmethod
    def _empty_result(n_paragraphs: int) -> Dict[str, Any]:
        return {
            "clusters": [-1] * n_paragraphs,
            "estimated_authors": 1,
            "anomaly_indices": [],
            "anomaly_count": 0,
            "boundaries": [],
            "boundary_count": 0,
            "noise_percentage": 0.0,
            "cluster_sizes": {},
            "confidence": "low",
            "noise_override": False,
            "too_short": True,
        }
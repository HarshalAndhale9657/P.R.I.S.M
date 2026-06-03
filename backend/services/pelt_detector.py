"""
P.R.I.S.M. — PELT Change-Point Detection Engine
=================================================
Sequential change-point detector using the PELT (Pruned Exact Linear Time)
algorithm from the `ruptures` library.

Unlike HDBSCAN (which clusters paragraphs by similarity, ignoring order),
PELT treats paragraphs as a sequential signal and detects positions where
the feature distribution shifts significantly.

This module passes the "deletion test" — it can be benchmarked independently
of HDBSCAN, enabling fair comparison in Phase 7 evaluation.

Pipeline: Feature Matrix (N×D) → PELT → Change Point Indices
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import ruptures as rpt
    RUPTURES_AVAILABLE = True
except ImportError:
    logger.warning("[P.R.I.S.M.] ruptures not installed. PELT detector unavailable. Run: pip install ruptures")
    RUPTURES_AVAILABLE = False


class PELTDetector:
    """
    Detects style change points in sequential paragraph features.
    Uses the PELT algorithm with configurable cost function and penalty.

    Key difference from HDBSCAN:
      - HDBSCAN ignores paragraph ORDER → groups by similarity
      - PELT respects paragraph ORDER → finds where the signal shifts

    Both approaches complement each other — the boundary_fusion module
    combines their outputs for higher-confidence detection.
    """

    def __init__(
        self,
        model: str = "rbf",
        min_size: int = 2,
        default_penalty: float = 1.0,
    ):
        """
        Args:
            model: Cost function for PELT.
                   "rbf" = radial basis function (detects distribution shifts)
                   "l2"  = least squares (detects mean shifts, faster)
            min_size: Minimum segment length between change points.
            default_penalty: Penalty parameter controlling sensitivity.
                            Lower = more change points, Higher = fewer.
        """
        self.model = model
        self.min_size = min_size
        self.default_penalty = default_penalty

    def detect(
        self,
        feature_matrix: np.ndarray,
        penalty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Detect style change points in the feature matrix.

        Args:
            feature_matrix: np.ndarray of shape (N, D) — one row per paragraph.
            penalty: Override penalty parameter. If None, uses default_penalty.

        Returns:
            Dict containing:
                - change_points: list of paragraph indices where style shifts
                - boundaries: list of boundary dicts (compatible with fusion module)
                - n_segments: number of segments detected
                - penalty_used: the penalty value that was applied
                - model: the cost function used
        """
        if not RUPTURES_AVAILABLE:
            logger.error("[P.R.I.S.M.] ruptures not installed — PELT detection skipped")
            return self._empty_result()

        n_paragraphs = feature_matrix.shape[0]

        if n_paragraphs < self.min_size * 2:
            logger.warning(
                f"[P.R.I.S.M.] Only {n_paragraphs} paragraphs — too few for PELT "
                f"(need >= {self.min_size * 2}). Returning no change points."
            )
            return self._empty_result()

        # Normalize features to prevent scale dominance
        col_std = np.std(feature_matrix, axis=0)
        col_std[col_std < 1e-10] = 1.0
        normalized = (feature_matrix - np.mean(feature_matrix, axis=0)) / col_std

        pen = penalty if penalty is not None else self.default_penalty

        try:
            algo = rpt.Pelt(model=self.model, min_size=self.min_size).fit(normalized)
            raw_change_points = algo.predict(pen=pen)

            # ruptures returns change points including the last index (= n), remove it
            change_points = [cp for cp in raw_change_points if cp < n_paragraphs]

            # Build boundary dicts (compatible with boundary_fusion.py)
            boundaries = []
            for cp in change_points:
                boundaries.append({
                    "after_paragraph": cp - 1,
                    "change_point_index": cp,
                    "detection_method": "pelt",
                    "model": self.model,
                    "penalty": pen,
                })

            logger.info(
                f"[P.R.I.S.M.] PELT ({self.model}): {len(change_points)} change points "
                f"detected with penalty={pen}"
            )

            return {
                "change_points": change_points,
                "boundaries": boundaries,
                "n_segments": len(change_points) + 1,
                "penalty_used": pen,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"[P.R.I.S.M.] PELT detection failed: {e}")
            return self._empty_result()

    def detect_with_multiple_penalties(
        self,
        feature_matrix: np.ndarray,
        penalties: List[float] = None,
    ) -> Dict[str, Any]:
        """
        Run PELT with multiple penalty values for hyperparameter analysis.
        Returns results for each penalty.
        """
        if penalties is None:
            penalties = [0.5, 1.0, 2.0, 5.0, 10.0]

        results = {}
        for pen in penalties:
            result = self.detect(feature_matrix, penalty=pen)
            results[str(pen)] = {
                "penalty": pen,
                "change_points": result["change_points"],
                "n_segments": result["n_segments"],
            }

        return results

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "change_points": [],
            "boundaries": [],
            "n_segments": 1,
            "penalty_used": None,
            "model": None,
        }

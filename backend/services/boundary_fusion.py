"""
P.R.I.S.M. — Boundary Fusion Module
=====================================
Fuses boundary detections from HDBSCAN and PELT into a unified,
confidence-tiered boundary list.

Confidence tiers:
  HIGH:   Both HDBSCAN and PELT agree (within ±1 paragraph tolerance)
  MEDIUM: Only one engine detected the boundary

This is the "deep module" in P.R.I.S.M.'s architecture — small interface,
significant implementation logic for matching and deduplication.
"""

import logging
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class BoundaryCorroboration(str, Enum):
    """Confidence level based on inter-engine agreement."""
    HIGH = "high"      # Both engines agree
    MEDIUM = "medium"  # Only one engine detected


class TieredBoundary:
    """A single boundary with corroboration metadata."""

    def __init__(
        self,
        position: int,
        corroboration: BoundaryCorroboration,
        detected_by: List[str],
    ):
        self.position = position
        self.corroboration = corroboration
        self.detected_by = detected_by

    def to_dict(self) -> Dict[str, Any]:
        return {
            "after_paragraph": self.position,
            "corroboration": self.corroboration.value,
            "detected_by": self.detected_by,
        }


class BoundaryFusion:
    """
    Fuses boundary detections from multiple engines into a unified list.

    The fusion algorithm:
    1. Collect boundary positions from HDBSCAN and PELT
    2. Match boundaries within ±tolerance paragraphs
    3. Matched boundaries → HIGH confidence
    4. Unmatched boundaries → MEDIUM confidence
    5. Deduplicate overlapping boundaries
    """

    def __init__(self, tolerance: int = 1):
        """
        Args:
            tolerance: Maximum paragraph offset for two boundaries to be
                       considered "agreeing". Default ±1 paragraph.
        """
        self.tolerance = tolerance

    def fuse(
        self,
        hdbscan_boundaries: List[int],
        pelt_boundaries: List[int],
    ) -> Dict[str, Any]:
        """
        Fuse boundary detections from HDBSCAN and PELT.

        Args:
            hdbscan_boundaries: Paragraph indices where HDBSCAN detects transitions.
            pelt_boundaries: Paragraph indices where PELT detects change points.

        Returns:
            Dict with:
                - boundaries: list of TieredBoundary dicts
                - high_confidence_count: number of HIGH boundaries
                - medium_confidence_count: number of MEDIUM boundaries
                - total_boundaries: total boundary count
                - agreement_rate: fraction of boundaries corroborated by both engines
        """
        if not hdbscan_boundaries and not pelt_boundaries:
            return self._empty_result()

        # Track which boundaries have been matched
        hdbscan_matched = set()
        pelt_matched = set()
        tiered_boundaries = []

        # Step 1: Find matching pairs (HIGH confidence)
        for hi, hb in enumerate(hdbscan_boundaries):
            for pi, pb in enumerate(pelt_boundaries):
                if pi not in pelt_matched and abs(hb - pb) <= self.tolerance:
                    # Match found — use the average position
                    avg_pos = round((hb + pb) / 2)
                    tiered_boundaries.append(TieredBoundary(
                        position=avg_pos,
                        corroboration=BoundaryCorroboration.HIGH,
                        detected_by=["hdbscan", "pelt"],
                    ))
                    hdbscan_matched.add(hi)
                    pelt_matched.add(pi)
                    break

        # Step 2: Add unmatched HDBSCAN boundaries (MEDIUM)
        for hi, hb in enumerate(hdbscan_boundaries):
            if hi not in hdbscan_matched:
                tiered_boundaries.append(TieredBoundary(
                    position=hb,
                    corroboration=BoundaryCorroboration.MEDIUM,
                    detected_by=["hdbscan"],
                ))

        # Step 3: Add unmatched PELT boundaries (MEDIUM)
        for pi, pb in enumerate(pelt_boundaries):
            if pi not in pelt_matched:
                tiered_boundaries.append(TieredBoundary(
                    position=pb,
                    corroboration=BoundaryCorroboration.MEDIUM,
                    detected_by=["pelt"],
                ))

        # Sort by position
        tiered_boundaries.sort(key=lambda b: b.position)

        # Deduplicate boundaries that are too close together
        tiered_boundaries = self._deduplicate(tiered_boundaries)

        high_count = sum(1 for b in tiered_boundaries if b.corroboration == BoundaryCorroboration.HIGH)
        medium_count = len(tiered_boundaries) - high_count
        total = len(tiered_boundaries)

        agreement_rate = high_count / max(total, 1)

        logger.info(
            f"[P.R.I.S.M.] Boundary fusion: {total} boundaries "
            f"({high_count} HIGH, {medium_count} MEDIUM, "
            f"agreement rate: {agreement_rate:.0%})"
        )

        return {
            "boundaries": [b.to_dict() for b in tiered_boundaries],
            "high_confidence_count": high_count,
            "medium_confidence_count": medium_count,
            "total_boundaries": total,
            "agreement_rate": round(agreement_rate, 4),
        }

    def _deduplicate(self, boundaries: List[TieredBoundary]) -> List[TieredBoundary]:
        """Remove boundaries that are too close together (within tolerance)."""
        if len(boundaries) <= 1:
            return boundaries

        deduplicated = [boundaries[0]]
        for b in boundaries[1:]:
            if abs(b.position - deduplicated[-1].position) > self.tolerance:
                deduplicated.append(b)
            else:
                # Keep the one with higher confidence
                if b.corroboration == BoundaryCorroboration.HIGH:
                    deduplicated[-1] = b

        return deduplicated

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "boundaries": [],
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "total_boundaries": 0,
            "agreement_rate": 1.0,
        }

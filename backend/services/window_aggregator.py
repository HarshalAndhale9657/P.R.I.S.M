"""
P.R.I.S.M. — Sliding Window Aggregator
========================================
Preprocesses short paragraphs into overlapping windows of sufficient length
for reliable stylometric feature extraction.

Problem: PAN 2023 paragraphs have a median of 41 words, but the FeatureEngine
needs 50+ words for meaningful extraction and 100+ for full extraction.
61% of PAN paragraphs produce all-zero feature vectors.

Solution: Merge adjacent paragraphs into overlapping windows of ~target_words,
extract features per-window, then map window-level change points back to
paragraph-level boundaries.

Pipeline position:
    Raw paragraphs → WindowAggregator → FeatureEngine → PELT/Distance → Fusion
"""

import logging
import numpy as np
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class WindowAggregator:
    """
    Merges adjacent paragraphs into overlapping windows for feature extraction.

    Each window spans one or more consecutive paragraphs and contains at least
    `target_words` words (when possible). Windows advance by `stride` paragraphs,
    creating overlap for boundary resolution.

    After detection, use `map_boundaries()` to convert window-level change points
    back to paragraph-level boundaries.
    """

    def __init__(self, target_words: int = 100, stride: int = 1):
        """
        Args:
            target_words: Minimum word count per window. Windows grow by
                         appending paragraphs until this threshold is met.
            stride: Number of paragraphs to advance between windows.
                   stride=1 gives maximum overlap and boundary resolution.
        """
        self.target_words = target_words
        self.stride = stride

    def build_windows(
        self, paragraphs: List[str]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Build overlapping windows from paragraph texts.

        Args:
            paragraphs: List of raw paragraph text strings.

        Returns:
            Tuple of:
              - windows: List of window metadata dicts with keys:
                  - start: first paragraph index (inclusive)
                  - end: last paragraph index (inclusive)
                  - text: concatenated text of all paragraphs in window
                  - word_count: total words in window
                  - n_paragraphs: number of paragraphs in window
              - window_texts: List of concatenated text strings (for FeatureEngine)
        """
        n = len(paragraphs)
        if n == 0:
            return [], []

        # Precompute word counts
        word_counts = [len(p.split()) for p in paragraphs]

        windows = []
        start = 0

        while start < n:
            # Grow window from 'start' until we reach target_words or end
            end = start
            total_words = word_counts[start]

            while total_words < self.target_words and end + 1 < n:
                end += 1
                total_words += word_counts[end]

            # Build the window
            window_text = " ".join(paragraphs[start:end + 1])
            windows.append({
                "start": start,
                "end": end,
                "text": window_text,
                "word_count": total_words,
                "n_paragraphs": end - start + 1,
            })

            # Advance by stride
            start += self.stride

            # If the last window already covers to the end, stop
            if end >= n - 1 and start > end - self.stride + 1:
                break

        window_texts = [w["text"] for w in windows]

        logger.debug(
            f"[WindowAggregator] {n} paragraphs → {len(windows)} windows "
            f"(target={self.target_words} words, stride={self.stride})"
        )

        return windows, window_texts

    def map_boundaries(
        self,
        window_boundaries: List[int],
        windows: List[Dict[str, Any]],
        n_paragraphs: int,
    ) -> List[int]:
        """
        Map window-level change points back to paragraph-level boundaries.

        A change point between window[i] and window[i+1] maps to the paragraph
        boundary at the midpoint of the overlap between those two windows.

        Args:
            window_boundaries: List of window indices where changes were detected.
                              A boundary at index i means a change between
                              window[i-1] and window[i].
            windows: Window metadata from build_windows().
            n_paragraphs: Total number of original paragraphs.

        Returns:
            List of paragraph-level boundary indices (sorted, deduplicated).
        """
        if not window_boundaries or not windows:
            return []

        para_boundaries = set()

        for wb in window_boundaries:
            if wb <= 0 or wb >= len(windows):
                continue

            prev_window = windows[wb - 1]
            curr_window = windows[wb]

            # The boundary falls between prev_window.end and curr_window.start
            # With stride=1, curr_window.start = prev_window.start + 1
            # The actual paragraph boundary is at curr_window.start
            boundary_para = curr_window["start"]

            if 0 < boundary_para < n_paragraphs:
                para_boundaries.add(boundary_para)

        return sorted(para_boundaries)


def extract_windowed_features(
    paragraphs: List[str],
    feature_engine,
    target_words: int = 100,
    stride: int = 1,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    Convenience function: build windows, extract features, return matrix + metadata.

    Args:
        paragraphs: List of paragraph text strings.
        feature_engine: FeatureEngine instance.
        target_words: Target word count per window.
        stride: Window stride.

    Returns:
        Tuple of (feature_matrix, windows_metadata).
        feature_matrix has shape (n_windows, n_features).
    """
    aggregator = WindowAggregator(target_words=target_words, stride=stride)
    windows, window_texts = aggregator.build_windows(paragraphs)

    if not window_texts:
        from services.feature_engine import FEATURE_NAMES
        return np.zeros((0, len(FEATURE_NAMES))), []

    # Extract features for each window
    para_dicts = [{"text": t} for t in window_texts]
    result = feature_engine.extract_all(para_dicts)

    return result["feature_matrix"], windows

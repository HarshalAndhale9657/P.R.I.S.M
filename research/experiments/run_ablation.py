"""
P.R.I.S.M. Research — Feature Ablation Study
=============================================
Evaluates which features contribute most to boundary detection.

Methodology:
  1. Run full pipeline with ALL 27 features on labeled dataset
  2. Leave-one-group-out: remove each feature group, measure F1 drop
  3. Rank features by their contribution to detection performance
  4. Select top ~20 features that maximize F1

Usage:
    python run_ablation.py
    python run_ablation.py --datasets-dir ../datasets --output-dir ../results
"""

import sys
import os
import json
import logging
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add backend to path for imports
BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.feature_engine import (
    FeatureEngine,
    FEATURE_NAMES,
    STRUCTURAL_FEATURES,
    TRIGRAM_FEATURES,
    FUNCWORD_FEATURES,
    PUNCT_FEATURES,
    HAPAX_FEATURES,
)
from evaluate_metrics import boundary_f1, clustering_metrics

# Import dataset loader
sys.path.insert(0, str(Path(__file__).parent))
from dataset_builder import DatasetLoader

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ─── Feature Groups for Ablation ─────────────────────────────────────────────

FEATURE_GROUPS = {
    "structural": STRUCTURAL_FEATURES,
    "char_trigrams": TRIGRAM_FEATURES,
    "function_words": FUNCWORD_FEATURES,
    "punctuation": PUNCT_FEATURES,
    "hapax": HAPAX_FEATURES,
}


def get_group_indices(group_names: List[str]) -> List[int]:
    """Get feature indices for the given feature names."""
    return [FEATURE_NAMES.index(name) for name in group_names if name in FEATURE_NAMES]


# ─── Simple Boundary Detector (for ablation — no HDBSCAN dependency) ────────

def detect_boundaries_simple(feature_matrix: np.ndarray, threshold_sigma: float = 1.5) -> List[int]:
    """
    Simple boundary detector for ablation testing.
    Detects boundaries by measuring feature distance between adjacent paragraphs.
    A boundary is flagged when the distance exceeds mean + threshold_sigma * std.

    This avoids HDBSCAN's DLL dependency and is deterministic.
    """
    if len(feature_matrix) < 2:
        return []

    # Compute pairwise distances between adjacent paragraphs
    distances = []
    for i in range(1, len(feature_matrix)):
        # Normalize to prevent scale dominance
        diff = feature_matrix[i] - feature_matrix[i - 1]
        dist = np.sqrt(np.sum(diff ** 2))
        distances.append(dist)

    if not distances or np.std(distances) < 1e-10:
        return []

    mean_dist = np.mean(distances)
    std_dist = np.std(distances)
    threshold = mean_dist + threshold_sigma * std_dist

    boundaries = []
    for i, dist in enumerate(distances):
        if dist > threshold:
            boundaries.append(i + 1)  # Boundary after paragraph i

    return boundaries


# ─── Ablation Runner ─────────────────────────────────────────────────────────

class AblationRunner:
    """
    Runs leave-one-group-out ablation study.
    For each feature group, removes it and measures the impact on boundary F1.
    """

    def __init__(self, datasets_dir: Path = None):
        self.engine = FeatureEngine()
        self.loader = DatasetLoader(datasets_dir)

    def run(self) -> Dict[str, Any]:
        """Run full ablation study and return results."""
        docs = self.loader.load_all()
        multi_author_docs = [d for d in docs if d["ground_truth"]["is_multi_author"]]

        logger.info(f"Loaded {len(docs)} documents ({len(multi_author_docs)} multi-author)")

        # Step 1: Baseline — all features
        logger.info("=== Running baseline (all 27 features) ===")
        baseline = self._evaluate_with_features(docs, list(range(len(FEATURE_NAMES))))
        logger.info(f"Baseline F1: {baseline['mean_boundary_f1']:.4f}")

        # Step 2: Leave-one-group-out
        logger.info("\n=== Leave-one-group-out ablation ===")
        ablation_results = {}

        for group_name, group_features in FEATURE_GROUPS.items():
            group_indices = get_group_indices(group_features)
            remaining_indices = [i for i in range(len(FEATURE_NAMES)) if i not in group_indices]

            result = self._evaluate_with_features(docs, remaining_indices)
            f1_drop = baseline["mean_boundary_f1"] - result["mean_boundary_f1"]

            ablation_results[group_name] = {
                "features_removed": group_features,
                "features_removed_count": len(group_features),
                "remaining_features": len(remaining_indices),
                "mean_boundary_f1": result["mean_boundary_f1"],
                "f1_drop": round(f1_drop, 4),
                "mean_doc_accuracy": result["mean_doc_accuracy"],
            }

            logger.info(
                f"  Without {group_name:20s} ({len(group_features):2d} feats): "
                f"F1={result['mean_boundary_f1']:.4f}  "
                f"drop={f1_drop:+.4f}"
            )

        # Step 3: Individual feature importance
        logger.info("\n=== Individual feature importance ===")
        individual_results = {}

        for i, feat_name in enumerate(FEATURE_NAMES):
            remaining = [j for j in range(len(FEATURE_NAMES)) if j != i]
            result = self._evaluate_with_features(docs, remaining)
            f1_drop = baseline["mean_boundary_f1"] - result["mean_boundary_f1"]

            individual_results[feat_name] = {
                "f1_without": result["mean_boundary_f1"],
                "f1_drop": round(f1_drop, 4),
            }

        # Rank by importance (largest F1 drop = most important)
        ranked = sorted(individual_results.items(), key=lambda x: x[1]["f1_drop"], reverse=True)
        logger.info("\nFeature ranking (by F1 drop when removed):")
        for rank, (name, data) in enumerate(ranked, 1):
            logger.info(f"  {rank:2d}. {name:30s} drop={data['f1_drop']:+.4f}")

        # Step 4: Select top features
        selected_features = [name for name, _ in ranked[:20]]

        return {
            "baseline": baseline,
            "group_ablation": ablation_results,
            "individual_importance": individual_results,
            "feature_ranking": [{"rank": i+1, "feature": name, "f1_drop": data["f1_drop"]} for i, (name, data) in enumerate(ranked)],
            "selected_features": selected_features,
            "total_features": len(FEATURE_NAMES),
            "selected_count": len(selected_features),
        }

    def _evaluate_with_features(
        self, docs: List[Dict], feature_indices: List[int]
    ) -> Dict[str, float]:
        """
        Run the detection pipeline using only the specified feature indices.
        Returns aggregate metrics across all documents.
        """
        boundary_f1_scores = []
        doc_correct = []

        for doc in docs:
            paragraphs = [{"text": p} for p in doc["paragraphs"]]
            gt = doc["ground_truth"]
            true_boundaries = gt.get("boundaries", [])
            is_multi_author = gt.get("is_multi_author", False)

            # Extract features
            result = self.engine.extract_all(paragraphs)
            matrix = result["feature_matrix"]

            if matrix.shape[0] < 2:
                continue

            # Select only specified features
            selected_matrix = matrix[:, feature_indices]

            # Normalize (zero-mean, unit-variance per column)
            col_std = np.std(selected_matrix, axis=0)
            col_std[col_std < 1e-10] = 1.0
            normalized = (selected_matrix - np.mean(selected_matrix, axis=0)) / col_std

            # Detect boundaries
            pred_boundaries = detect_boundaries_simple(normalized)

            # Compute metrics
            bf1 = boundary_f1(true_boundaries, pred_boundaries, tolerance=1)
            boundary_f1_scores.append(bf1["f1"])

            # Document-level accuracy
            pred_multi = len(pred_boundaries) > 0
            doc_correct.append(pred_multi == is_multi_author)

        return {
            "mean_boundary_f1": round(np.mean(boundary_f1_scores) if boundary_f1_scores else 0.0, 4),
            "mean_doc_accuracy": round(np.mean(doc_correct) if doc_correct else 0.0, 4),
            "n_evaluated": len(boundary_f1_scores),
        }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="P.R.I.S.M. Feature Ablation Study")
    parser.add_argument("--datasets-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(Path(__file__).parent.parent / "results" / "ablation"))
    args = parser.parse_args()

    datasets_dir = Path(args.datasets_dir) if args.datasets_dir else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = AblationRunner(datasets_dir)
    results = runner.run()

    # Save results
    output_path = output_dir / "ablation_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] Ablation complete!")
    print(f"   Results saved to: {output_path}")
    print(f"   Baseline F1: {results['baseline']['mean_boundary_f1']}")
    print(f"   Selected {results['selected_count']}/{results['total_features']} features")
    print(f"   Top 5: {results['selected_features'][:5]}")


if __name__ == "__main__":
    main()

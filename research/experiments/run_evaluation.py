"""
P.R.I.S.M. Research — Comprehensive Evaluation Suite
=====================================================
Phase 7: Run all baselines and statistical tests against the evaluation dataset.

TDD Approach (vertical slices):
  1. Baseline: Random detector → compute F1 → record
  2. HDBSCAN-only → compute F1 → record  
  3. PELT-only → compute F1 → record
  4. Fused (HDBSCAN+PELT) → compute F1 → record
  5. Paired t-test: Fused vs each baseline → confirm p < 0.05

Usage:
    python run_evaluation.py
    python run_evaluation.py --datasets-dir ../datasets --output-dir ../results/evaluation
"""

import sys
import os
import json
import logging
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.feature_engine import FeatureEngine, FEATURE_NAMES
from services.pelt_detector import PELTDetector
from services.boundary_fusion import BoundaryFusion
from services.window_aggregator import WindowAggregator
from services.embedding_similarity_detector import EmbeddingSimilarityDetector

# Import dataset loader
sys.path.insert(0, str(Path(__file__).parent))
from dataset_builder import DatasetLoader
from evaluate_metrics import boundary_f1, clustering_metrics

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ─── Baselines ───────────────────────────────────────────────────────────────

def random_baseline(n_paragraphs: int, seed: int = 42) -> List[int]:
    """Random baseline: flip a coin at each transition."""
    rng = np.random.RandomState(seed)
    boundaries = []
    for i in range(1, n_paragraphs):
        if rng.random() < 0.15:  # 15% chance of boundary at each position
            boundaries.append(i)
    return boundaries


def distance_baseline(feature_matrix: np.ndarray, sigma: float = 1.5) -> List[int]:
    """
    Simple distance-based baseline (same as in ablation).
    Detects boundaries where adjacent paragraph distance > mean + sigma * std.
    """
    if len(feature_matrix) < 2:
        return []
    
    # Normalize
    col_std = np.std(feature_matrix, axis=0)
    col_std[col_std < 1e-10] = 1.0
    normalized = (feature_matrix - np.mean(feature_matrix, axis=0)) / col_std
    
    distances = []
    for i in range(1, len(normalized)):
        diff = normalized[i] - normalized[i - 1]
        distances.append(float(np.sqrt(np.sum(diff ** 2))))
    
    if not distances or np.std(distances) < 1e-10:
        return []
    
    threshold = np.mean(distances) + sigma * np.std(distances)
    return [i + 1 for i, d in enumerate(distances) if d > threshold]


# ─── Evaluation Runner ───────────────────────────────────────────────────────

class EvaluationRunner:
    """
    Runs all detectors against the labeled dataset and computes metrics.
    Follows TDD vertical slice: one detector → one set of metrics → record.
    """

    def __init__(self, datasets_dir: Path = None, max_docs: int = 0):
        self.engine = FeatureEngine()
        self.loader = DatasetLoader(datasets_dir)
        self.pelt = PELTDetector(model="rbf", default_penalty=1.0)
        self.pelt_l2 = PELTDetector(model="l2", default_penalty=1.0)
        self.fusion = BoundaryFusion(tolerance=1)
        self.embed_detector = EmbeddingSimilarityDetector(sigma=1.0, min_similarity_drop=0.05)
        self.max_docs = max_docs

    def _stratified_sample(self, docs: List[Dict], max_docs: int) -> List[Dict]:
        """Stratified sampling: equal representation from each source category."""
        from collections import defaultdict
        buckets = defaultdict(list)
        for doc in docs:
            doc_id = doc.get("id", "")
            if "pan_easy" in doc_id:
                buckets["pan_easy"].append(doc)
            elif "pan_medium" in doc_id:
                buckets["pan_medium"].append(doc)
            elif "pan_hard" in doc_id:
                buckets["pan_hard"].append(doc)
            else:
                buckets["synthetic"].append(doc)

        per_bucket = max(1, max_docs // max(len(buckets), 1))
        rng = np.random.RandomState(42)
        sampled = []
        for key, bucket_docs in buckets.items():
            if len(bucket_docs) <= per_bucket:
                sampled.extend(bucket_docs)
            else:
                indices = rng.choice(len(bucket_docs), per_bucket, replace=False)
                sampled.extend([bucket_docs[i] for i in indices])
            logger.info(f"  Sampled {min(len(bucket_docs), per_bucket)}/{len(bucket_docs)} from {key}")

        rng.shuffle(sampled)
        return sampled

    def run(self) -> Dict[str, Any]:
        """Run full evaluation suite."""
        docs = self.loader.load_all()
        logger.info(f"Loaded {len(docs)} documents")

        if self.max_docs > 0 and len(docs) > self.max_docs:
            logger.info(f"Stratified sampling to {self.max_docs} documents...")
            docs = self._stratified_sample(docs, self.max_docs)
            logger.info(f"Sampled {len(docs)} documents")

        # Precompute feature matrices for all documents (per-paragraph)
        doc_features = []
        for doc in docs:
            paragraphs = [{"text": p} for p in doc["paragraphs"]]
            result = self.engine.extract_all(paragraphs)
            doc_features.append(result["feature_matrix"])

        # Precompute WINDOWED feature matrices + window metadata
        aggregator = WindowAggregator(target_words=100, stride=1)
        doc_windowed_features = []
        doc_windows = []
        for doc in docs:
            windows, window_texts = aggregator.build_windows(doc["paragraphs"])
            para_dicts = [{"text": t} for t in window_texts]
            result = self.engine.extract_all(para_dicts)
            doc_windowed_features.append(result["feature_matrix"])
            doc_windows.append(windows)

        results = {}

        # ── Slice 1: Random baseline ──────────────────────────────────────
        logger.info("\n=== Slice 1: Random Baseline ===")
        results["random"] = self._evaluate_detector(
            docs, doc_features,
            lambda mat, doc: random_baseline(len(mat)),
            "random"
        )

        # ── Slice 2: Distance baseline (per-paragraph) ───────────────────
        logger.info("\n=== Slice 2: Distance Baseline ===")
        results["distance"] = self._evaluate_detector(
            docs, doc_features,
            lambda mat, doc: distance_baseline(mat),
            "distance"
        )

        # ── Slice 3: PELT-rbf (per-paragraph) ────────────────────────────
        logger.info("\n=== Slice 3: PELT (rbf) ===")
        results["pelt_rbf"] = self._evaluate_detector(
            docs, doc_features,
            lambda mat, doc: self.pelt.detect(mat).get("change_points", []),
            "pelt_rbf"
        )

        # ── Slice 4: Fused per-paragraph (distance + PELT-rbf) ───────────
        logger.info("\n=== Slice 4: Fused per-paragraph ===")
        results["fused"] = self._evaluate_detector(
            docs, doc_features,
            lambda mat, doc: self._fused_detect(mat),
            "fused"
        )

        # ── Slice 5: Windowed Distance ───────────────────────────────────
        logger.info("\n=== Slice 5: Windowed Distance ===")
        results["w_distance"] = self._evaluate_windowed_detector(
            docs, doc_windowed_features, doc_windows,
            lambda mat, doc: distance_baseline(mat),
            "w_distance", aggregator
        )

        # ── Slice 6: Windowed PELT-rbf ───────────────────────────────────
        logger.info("\n=== Slice 6: Windowed PELT (rbf) ===")
        results["w_pelt_rbf"] = self._evaluate_windowed_detector(
            docs, doc_windowed_features, doc_windows,
            lambda mat, doc: self.pelt.detect(mat).get("change_points", []),
            "w_pelt_rbf", aggregator
        )

        # ── Slice 7: Windowed Fused (Distance + PELT-rbf) ────────────────
        logger.info("\n=== Slice 7: Windowed Fused ===")
        results["w_fused"] = self._evaluate_windowed_detector(
            docs, doc_windowed_features, doc_windows,
            lambda mat, doc: self._fused_detect(mat),
            "w_fused", aggregator
        )

        # ── Slice 8: Embedding Similarity (standalone) ───────────────────
        logger.info("\n=== Slice 8: Embedding Similarity ===")
        results["embed_sim"] = self._evaluate_embedding_detector(docs, "embed_sim")

        # ── Slice 9: Augmented Windowed (stylometric + embedding features) ─
        logger.info("\n=== Slice 9: Augmented Windowed PELT ===")
        doc_aug_features = []
        for doc in docs:
            paras = doc["paragraphs"]
            # Get windowed stylometric features
            windows, window_texts = aggregator.build_windows(paras)
            para_dicts = [{"text": t} for t in window_texts]
            result = self.engine.extract_all(para_dicts)
            stylo_matrix = result["feature_matrix"]
            # Get embedding similarity features for windows
            embed_feats = self.embed_detector.get_similarity_features(window_texts)
            # Augment: concatenate stylometric + embedding features
            if stylo_matrix.shape[0] == embed_feats.shape[0]:
                aug_matrix = np.hstack([stylo_matrix, embed_feats])
            else:
                aug_matrix = stylo_matrix
            doc_aug_features.append(aug_matrix)

        pelt_sensitive = PELTDetector(model="rbf", default_penalty=0.5)
        results["aug_w_pelt"] = self._evaluate_windowed_detector(
            docs, doc_aug_features, doc_windows,
            lambda mat, doc: pelt_sensitive.detect(mat).get("change_points", []),
            "aug_w_pelt", aggregator
        )

        # ── Slice 10: 3-Way Fusion (Distance + PELT + Embedding) ─────────
        logger.info("\n=== Slice 10: 3-Way Fusion ===")
        results["fusion3"] = self._evaluate_3way_fusion(
            docs, doc_windowed_features, doc_windows, aggregator, "fusion3"
        )

        # ── Statistical tests ────────────────────────────────────────────
        logger.info("\n=== Statistical Tests ===")
        stats = self._statistical_tests(results)
        
        # ── Summary table ────────────────────────────────────────────────
        logger.info("\n" + "=" * 70)
        logger.info("EVALUATION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"{'Detector':<20} {'Boundary F1':>12} {'Doc Acc':>10} {'Precision':>10} {'Recall':>10}")
        logger.info("-" * 70)
        for name, r in results.items():
            logger.info(
                f"{name:<20} {r['mean_boundary_f1']:>12.4f} "
                f"{r['doc_accuracy']:>10.4f} "
                f"{r['mean_precision']:>10.4f} "
                f"{r['mean_recall']:>10.4f}"
            )

        return {
            "detectors": results,
            "statistical_tests": stats,
            "dataset_size": len(docs),
            "feature_count": len(FEATURE_NAMES),
        }

    def _evaluate_detector(
        self, docs, doc_features, detect_fn, name: str
    ) -> Dict[str, Any]:
        """Evaluate a single detector across all documents."""
        f1_scores = []
        precisions = []
        recalls = []
        doc_correct = []
        per_doc = []

        for i, (doc, matrix) in enumerate(zip(docs, doc_features)):
            gt = doc["ground_truth"]
            true_boundaries = gt.get("boundaries", [])
            is_multi = gt.get("is_multi_author", False)

            if matrix.shape[0] < 2:
                continue

            pred_boundaries = detect_fn(matrix, doc)
            metrics = boundary_f1(true_boundaries, pred_boundaries, tolerance=1)
            
            f1_scores.append(metrics["f1"])
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])
            
            pred_multi = len(pred_boundaries) > 0
            doc_correct.append(pred_multi == is_multi)

            per_doc.append({
                "doc_id": doc["id"],
                "true_boundaries": true_boundaries,
                "pred_boundaries": pred_boundaries,
                "f1": metrics["f1"],
                "correct": pred_multi == is_multi,
            })

        result = {
            "mean_boundary_f1": round(float(np.mean(f1_scores)) if f1_scores else 0, 4),
            "std_boundary_f1": round(float(np.std(f1_scores)) if f1_scores else 0, 4),
            "mean_precision": round(float(np.mean(precisions)) if precisions else 0, 4),
            "mean_recall": round(float(np.mean(recalls)) if recalls else 0, 4),
            "doc_accuracy": round(float(np.mean(doc_correct)) if doc_correct else 0, 4),
            "n_evaluated": len(f1_scores),
            "f1_per_doc": [d["f1"] for d in per_doc],
            "per_doc_details": per_doc,
        }

        logger.info(
            f"  {name}: F1={result['mean_boundary_f1']:.4f} +/- {result['std_boundary_f1']:.4f}, "
            f"DocAcc={result['doc_accuracy']:.4f}"
        )
        return result

    def _fused_detect(self, feature_matrix: np.ndarray) -> List[int]:
        """Run distance + PELT + fusion pipeline."""
        dist_boundaries = distance_baseline(feature_matrix)
        pelt_result = self.pelt.detect(feature_matrix)
        pelt_boundaries = pelt_result.get("change_points", [])
        
        fusion_result = self.fusion.fuse(dist_boundaries, pelt_boundaries)
        return [b["after_paragraph"] for b in fusion_result.get("boundaries", [])]

    def _evaluate_windowed_detector(
        self, docs, doc_windowed_features, doc_windows, detect_fn, name, aggregator
    ) -> Dict[str, Any]:
        """Evaluate a detector on windowed features, mapping boundaries back to paragraphs."""
        f1_scores = []
        precisions = []
        recalls = []
        doc_correct = []
        per_doc = []

        for i, (doc, matrix, windows) in enumerate(zip(docs, doc_windowed_features, doc_windows)):
            gt = doc["ground_truth"]
            true_boundaries = gt.get("boundaries", [])
            is_multi = gt.get("is_multi_author", False)
            n_paras = len(doc["paragraphs"])

            if matrix.shape[0] < 2:
                continue

            # Detect on windowed features
            window_boundaries = detect_fn(matrix, doc)

            # Map back to paragraph-level
            pred_boundaries = aggregator.map_boundaries(window_boundaries, windows, n_paras)

            metrics = boundary_f1(true_boundaries, pred_boundaries, tolerance=1)

            f1_scores.append(metrics["f1"])
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])

            pred_multi = len(pred_boundaries) > 0
            doc_correct.append(pred_multi == is_multi)

            per_doc.append({
                "doc_id": doc["id"],
                "true_boundaries": true_boundaries,
                "pred_boundaries": pred_boundaries,
                "f1": metrics["f1"],
                "correct": pred_multi == is_multi,
            })

        result = {
            "mean_boundary_f1": round(float(np.mean(f1_scores)) if f1_scores else 0, 4),
            "std_boundary_f1": round(float(np.std(f1_scores)) if f1_scores else 0, 4),
            "mean_precision": round(float(np.mean(precisions)) if precisions else 0, 4),
            "mean_recall": round(float(np.mean(recalls)) if recalls else 0, 4),
            "doc_accuracy": round(float(np.mean(doc_correct)) if doc_correct else 0, 4),
            "n_evaluated": len(f1_scores),
            "f1_per_doc": [d["f1"] for d in per_doc],
            "per_doc_details": per_doc,
        }

        logger.info(
            f"  {name}: F1={result['mean_boundary_f1']:.4f} +/- {result['std_boundary_f1']:.4f}, "
            f"DocAcc={result['doc_accuracy']:.4f}"
        )
        return result

    def _evaluate_embedding_detector(self, docs, name: str) -> Dict[str, Any]:
        """Evaluate the embedding similarity detector directly on paragraphs."""
        f1_scores = []
        precisions = []
        recalls = []
        doc_correct = []
        per_doc = []

        for doc in docs:
            gt = doc["ground_truth"]
            true_boundaries = gt.get("boundaries", [])
            is_multi = gt.get("is_multi_author", False)
            paras = doc["paragraphs"]

            if len(paras) < 2:
                continue

            result = self.embed_detector.detect(paras)
            pred_boundaries = result.get("boundaries", [])

            metrics = boundary_f1(true_boundaries, pred_boundaries, tolerance=1)
            f1_scores.append(metrics["f1"])
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])

            pred_multi = len(pred_boundaries) > 0
            doc_correct.append(pred_multi == is_multi)
            per_doc.append({
                "doc_id": doc["id"],
                "true_boundaries": true_boundaries,
                "pred_boundaries": pred_boundaries,
                "f1": metrics["f1"],
                "correct": pred_multi == is_multi,
            })

        result = {
            "mean_boundary_f1": round(float(np.mean(f1_scores)) if f1_scores else 0, 4),
            "std_boundary_f1": round(float(np.std(f1_scores)) if f1_scores else 0, 4),
            "mean_precision": round(float(np.mean(precisions)) if precisions else 0, 4),
            "mean_recall": round(float(np.mean(recalls)) if recalls else 0, 4),
            "doc_accuracy": round(float(np.mean(doc_correct)) if doc_correct else 0, 4),
            "n_evaluated": len(f1_scores),
            "f1_per_doc": [d["f1"] for d in per_doc],
            "per_doc_details": per_doc,
        }
        logger.info(
            f"  {name}: F1={result['mean_boundary_f1']:.4f} +/- {result['std_boundary_f1']:.4f}, "
            f"DocAcc={result['doc_accuracy']:.4f}"
        )
        return result

    def _evaluate_3way_fusion(
        self, docs, doc_windowed_features, doc_windows, aggregator, name
    ) -> Dict[str, Any]:
        """3-way fusion: Windowed Distance + Windowed PELT + Embedding Similarity."""
        pelt_sensitive = PELTDetector(model="rbf", default_penalty=0.5)
        f1_scores = []
        precisions = []
        recalls = []
        doc_correct = []
        per_doc = []

        for i, (doc, matrix, windows) in enumerate(
            zip(docs, doc_windowed_features, doc_windows)
        ):
            gt = doc["ground_truth"]
            true_boundaries = gt.get("boundaries", [])
            is_multi = gt.get("is_multi_author", False)
            paras = doc["paragraphs"]
            n_paras = len(paras)

            if matrix.shape[0] < 2 or n_paras < 2:
                continue

            # Engine 1: Windowed Distance -> map back to paragraphs
            w_dist = distance_baseline(matrix)
            dist_para = aggregator.map_boundaries(w_dist, windows, n_paras)

            # Engine 2: Windowed PELT (lower penalty) -> map back
            w_pelt = pelt_sensitive.detect(matrix).get("change_points", [])
            pelt_para = aggregator.map_boundaries(w_pelt, windows, n_paras)

            # Engine 3: Embedding Similarity (directly on paragraphs)
            embed_result = self.embed_detector.detect(paras)
            embed_para = embed_result.get("boundaries", [])

            # 3-way vote: boundary if 2+ engines agree (with tolerance=1)
            all_candidates = set(dist_para) | set(pelt_para) | set(embed_para)
            pred_boundaries = []
            for p in sorted(all_candidates):
                votes = 0
                if any(abs(p - d) <= 1 for d in dist_para):
                    votes += 1
                if any(abs(p - d) <= 1 for d in pelt_para):
                    votes += 1
                if any(abs(p - d) <= 1 for d in embed_para):
                    votes += 1
                if votes >= 2:
                    pred_boundaries.append(p)

            # Fallback: if strict voting finds nothing, use embedding alone
            if not pred_boundaries and embed_para:
                pred_boundaries = embed_para

            metrics = boundary_f1(true_boundaries, pred_boundaries, tolerance=1)
            f1_scores.append(metrics["f1"])
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])

            pred_multi = len(pred_boundaries) > 0
            doc_correct.append(pred_multi == is_multi)
            per_doc.append({
                "doc_id": doc["id"],
                "true_boundaries": true_boundaries,
                "pred_boundaries": pred_boundaries,
                "f1": metrics["f1"],
                "correct": pred_multi == is_multi,
            })

        result = {
            "mean_boundary_f1": round(float(np.mean(f1_scores)) if f1_scores else 0, 4),
            "std_boundary_f1": round(float(np.std(f1_scores)) if f1_scores else 0, 4),
            "mean_precision": round(float(np.mean(precisions)) if precisions else 0, 4),
            "mean_recall": round(float(np.mean(recalls)) if recalls else 0, 4),
            "doc_accuracy": round(float(np.mean(doc_correct)) if doc_correct else 0, 4),
            "n_evaluated": len(f1_scores),
            "f1_per_doc": [d["f1"] for d in per_doc],
            "per_doc_details": per_doc,
        }
        logger.info(
            f"  {name}: F1={result['mean_boundary_f1']:.4f} +/- {result['std_boundary_f1']:.4f}, "
            f"DocAcc={result['doc_accuracy']:.4f}"
        )
        return result

    def _statistical_tests(self, results: Dict) -> Dict[str, Any]:
        """
        Run paired t-tests comparing fused detector vs baselines.
        Reports p-values and significance at alpha=0.05.
        """
        from scipy import stats as scipy_stats

        # Use windowed fused as primary if available, else fall back to fused
        primary = "fusion3" if "fusion3" in results else ("w_fused" if "w_fused" in results else "fused")
        primary_f1s = results[primary]["f1_per_doc"]
        tests = {}

        comparisons = [k for k in results.keys() if k != primary]
        for baseline_name in comparisons:
            baseline_f1s = results[baseline_name].get("f1_per_doc", [])
            
            n = min(len(primary_f1s), len(baseline_f1s))
            if n < 2:
                tests[f"{primary}_vs_{baseline_name}"] = {
                    "error": "Not enough paired samples",
                    "n_pairs": n,
                }
                continue

            t_stat, p_value = scipy_stats.ttest_rel(primary_f1s[:n], baseline_f1s[:n])
            significant = p_value < 0.05
            
            tests[f"{primary}_vs_{baseline_name}"] = {
                "t_statistic": round(float(t_stat), 4),
                "p_value": round(float(p_value), 6),
                "significant_at_005": significant,
                "n_pairs": n,
                "fused_mean": round(float(np.mean(primary_f1s[:n])), 4),
                "baseline_mean": round(float(np.mean(baseline_f1s[:n])), 4),
                "improvement": round(float(np.mean(primary_f1s[:n]) - np.mean(baseline_f1s[:n])), 4),
            }

            status = "SIGNIFICANT" if significant else "not significant"
            logger.info(
                f"  {primary} vs {baseline_name}: t={t_stat:.3f}, p={p_value:.4f} ({status}), "
                f"improvement={np.mean(primary_f1s[:n]) - np.mean(baseline_f1s[:n]):+.4f}"
            )

        return tests


# ─── Hyperparameter Sweep ───────────────────────────────────────────────────

class HyperparameterSweep:
    """
    Sweep PELT penalty and fusion tolerance to find optimal settings.
    """

    def __init__(self, datasets_dir: Path = None):
        self.engine = FeatureEngine()
        self.loader = DatasetLoader(datasets_dir)

    def sweep(
        self,
        penalties: List[float] = None,
        tolerances: List[int] = None,
    ) -> Dict[str, Any]:
        """Run parameter sweep and return best configuration."""
        if penalties is None:
            penalties = [0.5, 1.0, 2.0, 5.0, 10.0]
        if tolerances is None:
            tolerances = [0, 1, 2]

        docs = self.loader.load_all()
        
        # Precompute features
        doc_features = []
        for doc in docs:
            paragraphs = [{"text": p} for p in doc["paragraphs"]]
            result = self.engine.extract_all(paragraphs)
            doc_features.append(result["feature_matrix"])

        results = []
        best_f1 = -1
        best_config = None

        for pen in penalties:
            for tol in tolerances:
                pelt = PELTDetector(model="rbf", default_penalty=pen)
                fusion = BoundaryFusion(tolerance=tol)

                f1_scores = []
                for doc, matrix in zip(docs, doc_features):
                    if matrix.shape[0] < 2:
                        continue

                    gt = doc["ground_truth"]
                    true_b = gt.get("boundaries", [])

                    dist_b = distance_baseline(matrix)
                    pelt_b = pelt.detect(matrix).get("change_points", [])
                    fused = fusion.fuse(dist_b, pelt_b)
                    pred_b = [b["after_paragraph"] for b in fused.get("boundaries", [])]

                    metrics = boundary_f1(true_b, pred_b, tolerance=1)
                    f1_scores.append(metrics["f1"])

                mean_f1 = float(np.mean(f1_scores)) if f1_scores else 0
                
                config = {"penalty": pen, "tolerance": tol, "mean_f1": round(mean_f1, 4)}
                results.append(config)

                if mean_f1 > best_f1:
                    best_f1 = mean_f1
                    best_config = config

                logger.info(f"  penalty={pen}, tolerance={tol}: F1={mean_f1:.4f}")

        return {
            "sweep_results": results,
            "best_config": best_config,
            "n_configs_tested": len(results),
        }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="P.R.I.S.M. Evaluation Suite")
    parser.add_argument("--datasets-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(Path(__file__).parent.parent / "results" / "evaluation"))
    parser.add_argument("--sweep", action="store_true", help="Also run hyperparameter sweep")
    parser.add_argument("--max-docs", type=int, default=0, help="Max documents to evaluate (0 = all). Uses stratified sampling.")
    args = parser.parse_args()

    datasets_dir = Path(args.datasets_dir) if args.datasets_dir else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run evaluation
    runner = EvaluationRunner(datasets_dir, max_docs=args.max_docs)
    results = runner.run()

    # Save results
    eval_path = output_dir / "evaluation_results.json"
    with open(eval_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[OK] Evaluation saved to: {eval_path}")

    # Optional: hyperparameter sweep
    if args.sweep:
        logger.info("\n=== Hyperparameter Sweep ===")
        sweeper = HyperparameterSweep(datasets_dir)
        sweep_results = sweeper.sweep()

        sweep_path = output_dir / "hyperparameter_sweep.json"
        with open(sweep_path, "w") as f:
            json.dump(sweep_results, f, indent=2)
        print(f"[OK] Sweep saved to: {sweep_path}")
        print(f"    Best config: {sweep_results['best_config']}")


if __name__ == "__main__":
    main()

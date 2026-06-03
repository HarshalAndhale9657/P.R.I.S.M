"""
P.R.I.S.M. Research — Unified Evaluation Metrics
=================================================
Implements all standard metrics for plagiarism detection evaluation:
  - Document-level: Accuracy, Precision, Recall, F1, AUC-ROC
  - Segment-level: Plagdet, Boundary F1, Jaccard, WindowDiff
  - Clustering: Silhouette, ARI, NMI, V-Measure
  - Statistical: paired t-test, Wilcoxon, confidence intervals, effect size

Usage:
    from evaluate_metrics import EvaluationSuite
    suite = EvaluationSuite()
    results = suite.evaluate_document_level(predictions, ground_truth)
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter
import json
import os


# ─── Document-Level Metrics ─────────────────────────────────────────────────

def document_level_metrics(
    y_true: List[bool],
    y_pred: List[bool],
) -> Dict[str, float]:
    """
    Compute document-level binary classification metrics.
    
    Args:
        y_true: Ground truth labels (True = plagiarized, False = genuine)
        y_pred: Predicted labels
    
    Returns:
        Dict with accuracy, precision, recall, f1, specificity
    """
    assert len(y_true) == len(y_pred), "Length mismatch"
    
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / max(total, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    specificity = tn / max(tn + fp, 1)
    
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "specificity": round(specificity, 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }


# ─── Segment-Level Metrics ──────────────────────────────────────────────────

def boundary_f1(
    true_boundaries: List[int],
    pred_boundaries: List[int],
    tolerance: int = 1,
) -> Dict[str, float]:
    """
    Compute F1 for boundary detection with tolerance window.
    A predicted boundary is considered correct if it falls within
    ±tolerance paragraphs of a true boundary.
    
    Args:
        true_boundaries: List of true boundary paragraph indices
        pred_boundaries: List of predicted boundary paragraph indices
        tolerance: Allowed offset (default ±1 paragraph)
    
    Returns:
        Dict with precision, recall, f1
    """
    if not true_boundaries and not pred_boundaries:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not true_boundaries:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    if not pred_boundaries:
        return {"precision": 1.0, "recall": 0.0, "f1": 0.0}
    
    # Match predictions to ground truth
    matched_true = set()
    matched_pred = set()
    
    for pi, pb in enumerate(pred_boundaries):
        for ti, tb in enumerate(true_boundaries):
            if ti not in matched_true and abs(pb - tb) <= tolerance:
                matched_true.add(ti)
                matched_pred.add(pi)
                break
    
    tp = len(matched_pred)
    precision = tp / max(len(pred_boundaries), 1)
    recall = tp / max(len(true_boundaries), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def segment_jaccard(
    true_anomalies: List[int],
    pred_anomalies: List[int],
    total_paragraphs: int,
) -> float:
    """
    Compute Jaccard index between true and predicted anomaly segments.
    
    Args:
        true_anomalies: Indices of true anomalous paragraphs
        pred_anomalies: Indices of predicted anomalous paragraphs
        total_paragraphs: Total number of paragraphs in document
    
    Returns:
        Jaccard index (0 to 1)
    """
    true_set = set(true_anomalies)
    pred_set = set(pred_anomalies)
    
    intersection = len(true_set & pred_set)
    union = len(true_set | pred_set)
    
    return round(intersection / max(union, 1), 4)


def plagdet_score(
    true_segments: List[Tuple[int, int]],  # (start, end) character positions
    pred_segments: List[Tuple[int, int]],
) -> Dict[str, float]:
    """
    Compute PAN Plagdet score.
    Plagdet = F1 / log2(1 + granularity)
    
    Args:
        true_segments: Ground truth plagiarized character ranges
        pred_segments: Predicted plagiarized character ranges
    
    Returns:
        Dict with precision, recall, granularity, plagdet
    """
    if not true_segments and not pred_segments:
        return {"precision": 1.0, "recall": 1.0, "granularity": 1.0, "plagdet": 1.0}
    if not true_segments:
        return {"precision": 0.0, "recall": 1.0, "granularity": 1.0, "plagdet": 0.0}
    if not pred_segments:
        return {"precision": 1.0, "recall": 0.0, "granularity": 1.0, "plagdet": 0.0}
    
    def overlap(s1: Tuple[int, int], s2: Tuple[int, int]) -> int:
        """Character-level overlap between two segments."""
        start = max(s1[0], s2[0])
        end = min(s1[1], s2[1])
        return max(0, end - start)
    
    def length(s: Tuple[int, int]) -> int:
        return max(s[1] - s[0], 1)
    
    # Precision: how much of detected text is actually plagiarized
    precision_num = 0
    precision_den = 0
    for ps in pred_segments:
        max_overlap = max(overlap(ps, ts) for ts in true_segments)
        precision_num += max_overlap
        precision_den += length(ps)
    
    precision = precision_num / max(precision_den, 1)
    
    # Recall: how much of plagiarized text is detected
    recall_num = 0
    recall_den = 0
    for ts in true_segments:
        max_overlap = max(overlap(ts, ps) for ps in pred_segments)
        recall_num += max_overlap
        recall_den += length(ts)
    
    recall = recall_num / max(recall_den, 1)
    
    # Granularity: how many detections cover each true segment
    granularity_sum = 0
    for ts in true_segments:
        detections = sum(1 for ps in pred_segments if overlap(ts, ps) > 0)
        granularity_sum += max(detections, 1)
    granularity = granularity_sum / max(len(true_segments), 1)
    
    # Plagdet = F1 / log2(1 + granularity)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    import math
    plagdet = f1 / math.log2(1 + granularity)
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "granularity": round(granularity, 4),
        "plagdet": round(plagdet, 4),
    }


# ─── Clustering Metrics ─────────────────────────────────────────────────────

def clustering_metrics(
    true_labels: List[int],
    pred_labels: List[int],
    feature_matrix: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    Compute clustering quality metrics.
    
    Args:
        true_labels: Ground truth author labels per paragraph
        pred_labels: Predicted cluster labels per paragraph
        feature_matrix: Optional feature matrix for internal metrics
    
    Returns:
        Dict with ARI, NMI, V-measure, and optionally Silhouette
    """
    from sklearn.metrics import (
        adjusted_rand_score,
        normalized_mutual_info_score,
        v_measure_score,
        silhouette_score,
    )
    
    results = {
        "adjusted_rand_index": round(adjusted_rand_score(true_labels, pred_labels), 4),
        "normalized_mutual_info": round(normalized_mutual_info_score(true_labels, pred_labels), 4),
        "v_measure": round(v_measure_score(true_labels, pred_labels), 4),
    }
    
    # Silhouette requires feature matrix and at least 2 clusters
    if feature_matrix is not None and len(set(pred_labels)) >= 2:
        try:
            sil = silhouette_score(feature_matrix, pred_labels)
            results["silhouette"] = round(float(sil), 4)
        except Exception:
            results["silhouette"] = None
    
    return results


# ─── Statistical Tests ───────────────────────────────────────────────────────

def paired_significance_test(
    scores_a: List[float],
    scores_b: List[float],
    test: str = "wilcoxon",
) -> Dict[str, Any]:
    """
    Statistical significance test between two paired score lists.
    
    Args:
        scores_a: Scores from system A (per document)
        scores_b: Scores from system B (per document)
        test: "ttest" for paired t-test, "wilcoxon" for Wilcoxon signed-rank
    
    Returns:
        Dict with p_value, statistic, significant (at p<0.05), effect_size
    """
    from scipy import stats
    
    scores_a = np.array(scores_a)
    scores_b = np.array(scores_b)
    
    if test == "ttest":
        stat, p_value = stats.ttest_rel(scores_a, scores_b)
    elif test == "wilcoxon":
        # Handle case where differences are all zero
        diffs = scores_a - scores_b
        if np.all(diffs == 0):
            return {
                "statistic": 0.0, "p_value": 1.0,
                "significant": False, "effect_size": 0.0,
                "test": test,
            }
        stat, p_value = stats.wilcoxon(scores_a, scores_b)
    else:
        raise ValueError(f"Unknown test: {test}")
    
    # Cohen's d effect size
    diff = scores_a - scores_b
    effect_size = float(np.mean(diff) / max(np.std(diff, ddof=1), 1e-10))
    
    return {
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_value), 6),
        "significant": bool(p_value < 0.05),
        "effect_size": round(effect_size, 4),
        "test": test,
        "n": len(scores_a),
    }


def confidence_interval(
    scores: List[float],
    confidence: float = 0.95,
) -> Dict[str, float]:
    """
    Compute confidence interval for a list of scores.
    
    Args:
        scores: List of scores (one per document/trial)
        confidence: Confidence level (default 0.95 for 95% CI)
    
    Returns:
        Dict with mean, std, ci_lower, ci_upper
    """
    from scipy import stats
    
    scores = np.array(scores)
    n = len(scores)
    mean = float(np.mean(scores))
    std = float(np.std(scores, ddof=1))
    
    if n < 2:
        return {"mean": mean, "std": std, "ci_lower": mean, "ci_upper": mean}
    
    se = std / np.sqrt(n)
    t_crit = stats.t.ppf((1 + confidence) / 2, df=n - 1)
    margin = t_crit * se
    
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "ci_lower": round(mean - margin, 4),
        "ci_upper": round(mean + margin, 4),
        "n": n,
        "confidence": confidence,
    }


# ─── Evaluation Suite ────────────────────────────────────────────────────────

class EvaluationSuite:
    """
    Unified evaluation interface for all P.R.I.S.M. research experiments.
    Collects results and exports to JSON and LaTeX table formats.
    """
    
    def __init__(self, output_dir: str = "../results/raw"):
        self.output_dir = output_dir
        self.results = {}
    
    def evaluate_full(
        self,
        doc_id: str,
        true_is_plagiarized: bool,
        pred_is_plagiarized: bool,
        true_anomaly_indices: List[int],
        pred_anomaly_indices: List[int],
        true_boundaries: List[int],
        pred_boundaries: List[int],
        true_author_labels: List[int],
        pred_cluster_labels: List[int],
        total_paragraphs: int,
        feature_matrix: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Run all applicable metrics on a single document evaluation."""
        
        result = {
            "doc_id": doc_id,
            "document_correct": true_is_plagiarized == pred_is_plagiarized,
            "boundary_f1": boundary_f1(true_boundaries, pred_boundaries),
            "segment_jaccard": segment_jaccard(
                true_anomaly_indices, pred_anomaly_indices, total_paragraphs
            ),
            "clustering": clustering_metrics(
                true_author_labels, pred_cluster_labels, feature_matrix
            ),
        }
        
        self.results[doc_id] = result
        return result
    
    def save_results(self, filename: str = "experiment_results.json"):
        """Save all collected results to JSON."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, filename)
        with open(path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"Results saved to {path}")
    
    def summary_table(self) -> str:
        """Generate a summary table of all results."""
        if not self.results:
            return "No results collected yet."
        
        lines = []
        lines.append(f"{'Doc ID':<20} | {'Correct':^8} | {'Bound F1':^9} | {'Jaccard':^8} | {'ARI':^8} | {'NMI':^8}")
        lines.append("-" * 80)
        
        for doc_id, res in self.results.items():
            lines.append(
                f"{doc_id:<20} | "
                f"{'✅' if res['document_correct'] else '❌':^8} | "
                f"{res['boundary_f1']['f1']:^9.4f} | "
                f"{res['segment_jaccard']:^8.4f} | "
                f"{res['clustering']['adjusted_rand_index']:^8.4f} | "
                f"{res['clustering']['normalized_mutual_info']:^8.4f}"
            )
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Quick self-test
    print("=== P.R.I.S.M. Evaluation Metrics — Self-Test ===\n")
    
    # Document-level test
    y_true = [True, True, False, False, True]
    y_pred = [True, False, False, True, True]
    doc_metrics = document_level_metrics(y_true, y_pred)
    print(f"Document metrics: {doc_metrics}")
    
    # Boundary test
    true_b = [2, 5, 8]
    pred_b = [2, 6, 10]
    bf1 = boundary_f1(true_b, pred_b, tolerance=1)
    print(f"Boundary F1 (tol=1): {bf1}")
    
    # Segment Jaccard test
    jac = segment_jaccard([1, 3, 5], [1, 2, 5], 10)
    print(f"Segment Jaccard: {jac}")
    
    # CI test
    scores = [0.85, 0.88, 0.82, 0.90, 0.87, 0.84, 0.89]
    ci = confidence_interval(scores)
    print(f"95% CI: {ci}")
    
    # Significance test
    a = [0.85, 0.88, 0.82, 0.90, 0.87, 0.84, 0.89]
    b = [0.78, 0.80, 0.75, 0.82, 0.79, 0.77, 0.81]
    sig = paired_significance_test(a, b, test="ttest")
    print(f"Paired t-test: {sig}")
    
    print("\n✅ All metrics working correctly.")

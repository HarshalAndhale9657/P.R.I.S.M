"""
P.R.I.S.M. Research — Publication Figure Generator
====================================================
Generates IEEE-quality figures from evaluation results for the paper.

Figures produced:
  1. Detector comparison bar chart (F1, Precision, Recall)
  2. Per-difficulty breakdown (Easy/Medium/Hard)
  3. F1 distribution box plots
  4. Statistical significance heatmap

Usage:
    python generate_figures.py
    python generate_figures.py --results ../results/evaluation/evaluation_results.json
"""

import json
import sys
import logging
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ─── IEEE-quality style ──────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

# Color palette — professional, colorblind-friendly
COLORS = {
    "random": "#95a5a6",
    "distance": "#3498db",
    "pelt_rbf": "#e67e22",
    "pelt_l2": "#9b59b6",
    "fused": "#2ecc71",
}

LABELS = {
    "random": "Random",
    "distance": "Distance",
    "pelt_rbf": "PELT (RBF)",
    "pelt_l2": "PELT (L2)",
    "fused": "PRISM Fused",
}


def load_results(results_path: Path) -> dict:
    """Load evaluation results JSON."""
    with open(results_path, "r") as f:
        return json.load(f)


# ═════════════════════════════════════════════════════════════════════════════
# Figure 1: Detector Comparison Bar Chart
# ═════════════════════════════════════════════════════════════════════════════

def fig_detector_comparison(results: dict, output_dir: Path):
    """Bar chart comparing all detectors on F1, Precision, Recall, Doc Accuracy."""
    detectors = results.get("detectors", {})
    if not detectors:
        logger.warning("No detector results found")
        return

    names = list(detectors.keys())
    metrics = ["mean_boundary_f1", "mean_precision", "mean_recall", "doc_accuracy"]
    metric_labels = ["Boundary F1", "Precision", "Recall", "Doc Accuracy"]

    fig, ax = plt.subplots(figsize=(7, 3.5))

    x = np.arange(len(metrics))
    width = 0.15
    offsets = np.linspace(-(len(names)-1)*width/2, (len(names)-1)*width/2, len(names))

    for i, name in enumerate(names):
        values = [detectors[name].get(m, 0) for m in metrics]
        bars = ax.bar(
            x + offsets[i], values, width,
            label=LABELS.get(name, name),
            color=COLORS.get(name, "#333"),
            edgecolor="white", linewidth=0.5,
            zorder=3,
        )
        # Value labels on bars
        for bar, val in zip(bars, values):
            if val > 0.02:
                ax.text(
                    bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=6,
                )

    ax.set_xlabel("Metric")
    ax.set_ylabel("Score")
    ax.set_title("P.R.I.S.M. Detector Comparison (PAN 2023)")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.set_ylim(0, 1.15)
    ax.legend(loc="upper right", ncol=2, framealpha=0.9)
    ax.set_axisbelow(True)

    path = output_dir / "fig1_detector_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info(f"Saved: {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 2: Per-Difficulty Breakdown
# ═════════════════════════════════════════════════════════════════════════════

def fig_difficulty_breakdown(results: dict, output_dir: Path):
    """Grouped bar chart: F1 per detector, split by easy/medium/hard."""
    detectors = results.get("detectors", {})
    if not detectors:
        return

    difficulties = ["easy", "medium", "hard"]
    diff_labels = ["Easy (Dataset 1)", "Medium (Dataset 2)", "Hard (Dataset 3)"]

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), sharey=True)

    for ax, diff, diff_label in zip(axes, difficulties, diff_labels):
        detector_f1s = {}
        for det_name, det_data in detectors.items():
            # Filter per_doc_details by difficulty
            per_doc = det_data.get("per_doc_details", [])
            diff_f1s = [
                d["f1"] for d in per_doc
                if f"pan_{diff}" in d.get("doc_id", "")
            ]
            if diff_f1s:
                detector_f1s[det_name] = np.mean(diff_f1s)

        if not detector_f1s:
            ax.set_title(diff_label)
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            continue

        names = list(detector_f1s.keys())
        values = list(detector_f1s.values())
        colors = [COLORS.get(n, "#333") for n in names]
        labels = [LABELS.get(n, n) for n in names]

        bars = ax.bar(range(len(names)), values, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
        ax.set_title(diff_label, fontsize=10)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_ylim(0, 1.0)
        ax.set_axisbelow(True)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=6)

    axes[0].set_ylabel("Mean Boundary F1")
    fig.suptitle("Detection Performance by Difficulty Level", fontsize=12, y=1.02)
    fig.tight_layout()

    path = output_dir / "fig2_difficulty_breakdown.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info(f"Saved: {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 3: F1 Distribution Box Plots
# ═════════════════════════════════════════════════════════════════════════════

def fig_f1_boxplots(results: dict, output_dir: Path):
    """Box plots showing F1 distribution across all documents per detector."""
    detectors = results.get("detectors", {})
    if not detectors:
        return

    fig, ax = plt.subplots(figsize=(6, 3.5))

    data = []
    labels = []
    colors = []
    for name in detectors:
        f1s = detectors[name].get("f1_per_doc", [])
        if f1s:
            data.append(f1s)
            labels.append(LABELS.get(name, name))
            colors.append(COLORS.get(name, "#333"))

    if not data:
        plt.close(fig)
        return

    bp = ax.boxplot(
        data, patch_artist=True, labels=labels,
        medianprops=dict(color="black", linewidth=1.5),
        whiskerprops=dict(linewidth=0.8),
        capprops=dict(linewidth=0.8),
        flierprops=dict(marker="o", markersize=2, alpha=0.3),
    )

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_ylabel("Boundary F1 Score")
    ax.set_title("F1 Score Distribution Across Documents")
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_axisbelow(True)

    # Add mean markers
    for i, d in enumerate(data):
        ax.scatter(i + 1, np.mean(d), marker="D", color="red", s=20, zorder=5, label="Mean" if i == 0 else "")

    ax.legend(loc="upper left", fontsize=7)
    fig.tight_layout()

    path = output_dir / "fig3_f1_boxplots.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info(f"Saved: {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 4: Statistical Significance Table/Heatmap
# ═════════════════════════════════════════════════════════════════════════════

def fig_significance(results: dict, output_dir: Path):
    """Heatmap-style table showing p-values and significance markers."""
    stats = results.get("statistical_tests", {})
    if not stats:
        logger.warning("No statistical tests found")
        return

    fig, ax = plt.subplots(figsize=(5, 2.5))
    ax.axis("off")

    headers = ["Comparison", "t-stat", "p-value", "Improvement", "Significant"]
    rows = []
    cell_colors = []

    for test_name, test_data in stats.items():
        if "error" in test_data:
            continue

        comparison = test_name.replace("fused_vs_", "Fused vs ")
        comparison = comparison.replace("_", " ").title()
        t_stat = f"{test_data.get('t_statistic', 0):.3f}"
        p_val = test_data.get("p_value", 1)
        p_str = f"{p_val:.4f}" if p_val >= 0.0001 else f"{p_val:.2e}"
        improvement = f"{test_data.get('improvement', 0):+.4f}"
        sig = "Yes ✓" if test_data.get("significant_at_005", False) else "No"

        rows.append([comparison, t_stat, p_str, improvement, sig])
        
        if test_data.get("significant_at_005", False):
            cell_colors.append(["#e8f5e9"] * 5)
        else:
            cell_colors.append(["#fff3e0"] * 5)

    if not rows:
        plt.close(fig)
        return

    table = ax.table(
        cellText=rows,
        colLabels=headers,
        cellColours=cell_colors,
        colColours=["#eceff1"] * 5,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.2, 1.4)

    ax.set_title("Statistical Significance Tests (Paired t-test, α=0.05)", fontsize=10, pad=10)
    fig.tight_layout()

    path = output_dir / "fig4_significance.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info(f"Saved: {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Figure 5: Dataset Composition
# ═════════════════════════════════════════════════════════════════════════════

def fig_dataset_composition(results: dict, output_dir: Path):
    """Pie chart showing dataset composition by source/difficulty."""
    detectors = results.get("detectors", {})
    
    # Get any detector's per_doc_details to count
    per_doc = []
    for det_data in detectors.values():
        per_doc = det_data.get("per_doc_details", [])
        if per_doc:
            break

    if not per_doc:
        return

    # Count by source
    counts = defaultdict(int)
    for doc in per_doc:
        doc_id = doc.get("doc_id", "")
        if "pan_easy" in doc_id:
            counts["PAN Easy"] += 1
        elif "pan_medium" in doc_id:
            counts["PAN Medium"] += 1
        elif "pan_hard" in doc_id:
            counts["PAN Hard"] += 1
        elif "synthetic" in doc_id:
            if "genuine" in doc_id:
                counts["Synthetic (Single)"] += 1
            else:
                counts["Synthetic (Multi)"] += 1

    if not counts:
        return

    fig, ax = plt.subplots(figsize=(4, 4))
    pie_colors = ["#2ecc71", "#3498db", "#e74c3c", "#f39c12", "#95a5a6"]

    wedges, texts, autotexts = ax.pie(
        counts.values(), labels=counts.keys(), autopct="%1.1f%%",
        colors=pie_colors[:len(counts)],
        startangle=90, pctdistance=0.75,
        textprops={"fontsize": 8},
    )

    for autotext in autotexts:
        autotext.set_fontsize(7)

    ax.set_title(f"Evaluation Dataset Composition\n(N={sum(counts.values())})", fontsize=10)
    fig.tight_layout()

    path = output_dir / "fig5_dataset_composition.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info(f"Saved: {path}")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate publication figures")
    parser.add_argument(
        "--results",
        type=str,
        default=str(Path(__file__).parent.parent / "results" / "evaluation" / "evaluation_results.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).parent.parent / "results" / "figures"),
    )
    args = parser.parse_args()

    results_path = Path(args.results)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not results_path.exists():
        logger.error(f"Results file not found: {results_path}")
        logger.info("Run 'python run_evaluation.py' first to generate evaluation results.")
        sys.exit(1)

    logger.info(f"Loading results from: {results_path}")
    results = load_results(results_path)

    n_docs = results.get("dataset_size", "?")
    logger.info(f"Dataset size: {n_docs} documents")

    # Generate all figures
    fig_detector_comparison(results, output_dir)
    fig_difficulty_breakdown(results, output_dir)
    fig_f1_boxplots(results, output_dir)
    fig_significance(results, output_dir)
    fig_dataset_composition(results, output_dir)

    logger.info(f"\n[OK] All figures saved to: {output_dir}")
    logger.info("Include these in your IEEE draft with:")
    logger.info(r"  \includegraphics[width=\columnwidth]{figures/fig1_detector_comparison.png}")


if __name__ == "__main__":
    main()

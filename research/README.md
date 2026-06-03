# P.R.I.S.M. Research — Academic Paper Development

## Structure

```
research/
├── README.md                        # This file
├── literature_review/
│   ├── reading_notes.md             # Structured notes per paper
│   ├── related_work_draft.md        # Draft related work section
│   └── gap_analysis.md              # Where PRISM fills gaps in literature
├── datasets/
│   ├── ground_truth/                # Annotated ground truth corpus
│   ├── stitched/                    # Synthetic stitched documents
│   ├── genuine/                     # Verified single-author documents
│   ├── ai_mixed/                    # Human+AI mixed documents
│   └── edge_cases/                  # Short, multi-column, math-heavy, etc.
├── experiments/
│   ├── run_ablation.py              # Ablation study (Table 2)
│   ├── run_baselines.py             # Baseline comparisons (Table 1)
│   ├── run_hyperparameter_sweep.py  # Grid search
│   ├── run_obfuscation_test.py      # Paraphraser resistance
│   ├── run_cross_domain.py          # Domain generalization
│   ├── run_scalability.py           # Runtime analysis
│   ├── run_burstiness_validation.py # AI detection validation
│   ├── run_triplet_evaluation.py    # Idea Triplet effectiveness
│   ├── evaluate_metrics.py          # Unified metrics (Plagdet, F1, ARI)
│   ├── statistical_tests.py         # p-values, CIs, effect sizes
│   ├── generate_figures.py          # Publication-quality matplotlib plots
│   ├── generate_tables.py           # LaTeX table generation
│   └── run_all.py                   # Master experiment runner
├── results/
│   ├── tables/                      # Generated LaTeX tables
│   ├── figures/                     # Generated plots (PDF + PNG)
│   └── raw/                         # Raw JSON results per experiment
├── analysis/
│   └── statistical_analysis.md      # Statistical analysis writeup
├── paper/
│   ├── main.tex                     # LaTeX paper source
│   ├── references.bib               # BibTeX references
│   ├── figures/                     # Figures embedded in paper
│   └── acl2023.sty                  # Conference style file
└── supplementary/
    ├── hyperparameter_plots/        # Full sensitivity analysis
    ├── ablation_details/            # Per-component ablation details
    └── example_reports/             # Sample forensic reports
```

## Research Questions

1. **RQ1:** Does hybrid stylometric-semantic feature fusion improve detection over single-modality approaches?
2. **RQ2:** Can HDBSCAN noise detection serve as unsupervised authorship anomaly detection?
3. **RQ3:** Does Idea Triplet extraction resist AI paraphrasers?
4. **RQ4:** Does citation temporal forensics corroborate stylometric anomalies?
5. **RQ5:** Is burstiness a reliable AI-generation detector within mixed documents?

## Quick Start

```bash
# Install research dependencies
pip install pytest scipy matplotlib seaborn pandas tabulate

# Run all experiments
cd research/experiments
python run_all.py

# Generate paper figures
python generate_figures.py

# Run statistical tests
python statistical_tests.py
```

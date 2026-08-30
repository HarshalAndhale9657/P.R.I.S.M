"""
P.R.I.S.M. evaluation harness (ADR-0015/0016).

Pluggable, dataset-agnostic measurement of the pipeline's paraphrase pillar
against ready-made PUBLIC datasets (PAWS/MRPC/STS-B/QQP/PAWS-X — no PAN).

    from eval import metrics
    from eval.pairs import load_dataset
    from eval.scorer import score_pairs

CLI:
    python -m eval.run_pairs [datasets...] [--gate]
    python -m eval.fetch_datasets <name> [--split ... --limit ...]

Note: `eval.metrics` and `eval.pairs` are import-light (stdlib only); `eval.scorer`
pulls numpy + the model lazily, so metrics/loaders stay unit-testable without them.
"""
__all__ = ["metrics", "pairs", "scorer"]

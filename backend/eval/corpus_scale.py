"""
P.R.I.S.M. — Corpus-scale evaluation (ADR-0024)
================================================
Everything measured so far scores **one pair at a time**. The matcher does not: for
each document sentence it takes the **maximum similarity over every source sentence**.
With a corpus of N sentences that is N chances to score high, so the top score drifts
upward with N — the classic multiple-comparisons effect. ADR-0017 flagged this and
said the pairwise-calibrated cutoff (0.78) is therefore a **lower bound**, but the
size of the effect was never measured. This module measures it.

Method — deliberately simple so the number is trustworthy:

* Build a **distractor corpus** of N sentences that are unrelated to the query
  sentences (drawn from other pairs in the dataset).
* **Negative queries**: sentences whose paraphrase is *absent* from the corpus. Every
  flag is a false positive by construction, so the flag rate **is** the FPR.
* **Positive queries** (optional): the corpus additionally contains each query's true
  paraphrase, so the flag rate is recall at that corpus size.
* Sweep N and report FPR/recall per threshold. The gap between the pairwise number
  and the N-sentence number is the inflation the product actually lives with.

This is the *paraphrase pillar under corpus conditions*, not the whole product: it
skips verbatim matching, the relevance budget and reranking. It answers exactly one
question — how far does max-over-N move the operating point — and nothing more.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from .pairs import PairCase


@dataclass
class ScaleResult:
    corpus_size: int
    threshold: float
    n_negative_queries: int
    n_positive_queries: int
    false_positives: int
    true_positives: int
    fpr: float
    recall: float
    mean_max_negative: float          # mean of the top score for a query with no true match
    p95_max_negative: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScaleReport:
    dataset: str
    model_key: str
    corpus_sizes: List[int]
    thresholds: List[float]
    results: List[ScaleResult] = field(default_factory=list)

    def at(self, corpus_size: int, threshold: float) -> Optional[ScaleResult]:
        for r in self.results:
            if r.corpus_size == corpus_size and abs(r.threshold - threshold) < 1e-9:
                return r
        return None

    def threshold_for_fpr(self, corpus_size: int, max_fpr: float) -> Optional[float]:
        """Lowest swept threshold whose FPR is within budget at this corpus size."""
        candidates = sorted((r for r in self.results if r.corpus_size == corpus_size and r.fpr <= max_fpr),
                            key=lambda r: r.threshold)
        return candidates[0].threshold if candidates else None

    def as_dict(self) -> dict:
        return {"dataset": self.dataset, "model_key": self.model_key,
                "corpus_sizes": self.corpus_sizes, "thresholds": self.thresholds,
                "results": [r.as_dict() for r in self.results]}


def build_probe(
    pairs: Sequence[PairCase],
    *,
    n_queries: int = 200,
    max_corpus: int = 6000,
    seed: int = 0,
) -> tuple[List[str], List[str], List[str]]:
    """Return (negative_queries, positive_queries, distractors).

    `negative_queries` have no paraphrase anywhere in the distractor pool; each
    `positive_queries[i]` has its true paraphrase at `positives_truth[i]` (returned by
    `build_probe_with_truth`). Kept deterministic via `seed`.
    """
    neg_q, pos_q, _truth, distractors = build_probe_with_truth(
        pairs, n_queries=n_queries, max_corpus=max_corpus, seed=seed)
    return neg_q, pos_q, distractors


def build_probe_with_truth(
    pairs: Sequence[PairCase],
    *,
    n_queries: int = 200,
    max_corpus: int = 6000,
    seed: int = 0,
) -> tuple[List[str], List[str], List[str], List[str]]:
    """(negative_queries, positive_queries, positive_truths, distractors)."""
    rng = random.Random(seed)
    positives = [p for p in pairs if p.label == 1]
    pool = list(pairs)
    rng.shuffle(pool)
    rng.shuffle(positives)

    n_pos = min(n_queries, len(positives))
    pos_pairs = positives[:n_pos]
    pos_q = [p.a for p in pos_pairs]
    pos_truth = [p.b for p in pos_pairs]

    used = {p.a for p in pos_pairs} | set(pos_truth)
    # Negative queries: `a` sides not involved in the positive probes. Their partners are
    # deliberately excluded from the distractor pool, so nothing in the corpus paraphrases them.
    neg_q, excluded = [], set()
    for p in pool:
        if len(neg_q) >= n_queries:
            break
        if p.a in used or p.a in excluded:
            continue
        neg_q.append(p.a)
        excluded.add(p.a)
        excluded.add(p.b)          # never let a negative query's own partner into the corpus

    distractors: List[str] = []
    seen = set(neg_q) | set(pos_q) | set(pos_truth)
    for p in pool:
        for text in (p.a, p.b):
            if len(distractors) >= max_corpus:
                break
            if text in seen or text in excluded:
                continue
            distractors.append(text)
            seen.add(text)
    return neg_q, pos_q, pos_truth, distractors


def measure(
    pairs: Sequence[PairCase],
    *,
    embed,
    corpus_sizes: Sequence[int] = (100, 500, 1000, 3000, 6000),
    thresholds: Sequence[float] = (0.66, 0.70, 0.74, 0.78, 0.82, 0.86, 0.90),
    n_queries: int = 200,
    seed: int = 0,
    dataset: str = "",
    model_key: str = "bi-encoder",
) -> ScaleReport:
    """Measure FPR/recall vs corpus size. `embed(texts) -> (n, dim)` array.

    Everything is embedded once and sliced per corpus size, so a sweep costs one pass.
    """
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    sizes = sorted({int(n) for n in corpus_sizes if n > 0})
    max_needed = max(sizes)
    neg_q, pos_q, pos_truth, distractors = build_probe_with_truth(
        pairs, n_queries=n_queries, max_corpus=max_needed, seed=seed)
    if not neg_q or not distractors:
        raise ValueError("not enough data to build a corpus-scale probe")

    neg_emb = np.asarray(embed(neg_q), dtype=np.float32)
    pos_emb = np.asarray(embed(pos_q), dtype=np.float32) if pos_q else None
    dis_emb = np.asarray(embed(distractors), dtype=np.float32)
    truth_emb = np.asarray(embed(pos_truth), dtype=np.float32) if pos_truth else None

    neg_sims_full = cosine_similarity(neg_emb, dis_emb)                       # (Q, D)
    pos_vs_dis = cosine_similarity(pos_emb, dis_emb) if pos_emb is not None else None
    # A positive query's own truth sentence is always in the corpus, whatever its size.
    pos_vs_truth = (np.sum(pos_emb * truth_emb, axis=1) /
                    (np.linalg.norm(pos_emb, axis=1) * np.linalg.norm(truth_emb, axis=1) + 1e-12)
                    ) if pos_emb is not None else None

    report = ScaleReport(dataset=dataset, model_key=model_key,
                         corpus_sizes=sizes, thresholds=list(thresholds))
    for n in sizes:
        n_eff = min(n, dis_emb.shape[0])
        neg_max = neg_sims_full[:, :n_eff].max(axis=1)
        if pos_vs_dis is not None:
            # corpus = n_eff distractors + the true paraphrase
            pos_max = np.maximum(pos_vs_dis[:, :n_eff].max(axis=1), pos_vs_truth)
        else:
            pos_max = np.empty(0, dtype=np.float32)
        for t in thresholds:
            fp = int((neg_max >= t).sum())
            tp = int((pos_max >= t).sum()) if pos_max.size else 0
            report.results.append(ScaleResult(
                corpus_size=n_eff,
                threshold=float(t),
                n_negative_queries=len(neg_q),
                n_positive_queries=len(pos_q),
                false_positives=fp,
                true_positives=tp,
                fpr=round(fp / len(neg_q), 4),
                recall=round(tp / len(pos_q), 4) if pos_q else 0.0,
                mean_max_negative=round(float(neg_max.mean()), 4),
                p95_max_negative=round(float(np.percentile(neg_max, 95)), 4),
            ))
    return report


def inflation_table(report: ScaleReport) -> List[Dict[str, float]]:
    """How the top score for a *no-true-match* query drifts up as the corpus grows."""
    seen: Dict[int, ScaleResult] = {}
    for r in report.results:
        seen.setdefault(r.corpus_size, r)
    base = min(seen)
    rows = []
    for n in sorted(seen):
        rows.append({
            "corpus_size": n,
            "mean_max_negative": seen[n].mean_max_negative,
            "p95_max_negative": seen[n].p95_max_negative,
            "drift_vs_smallest": round(seen[n].mean_max_negative - seen[base].mean_max_negative, 4),
        })
    return rows

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

**Two distractor modes** (ADR-0025), because *which* N sentences you compare against
matters as much as how many:

* ``random`` — the ADR-0024 probe. Distractors are drawn arbitrarily, so they are
  topically unrelated to the query. This is the **floor** of the effect: nothing in
  production picks sources this badly.
* ``retrieved`` — the pool is ordered by **descending similarity to the manuscript**
  (max cosine to any query sentence) and the corpus is a prefix of that ranking. This
  is how the product actually assembles a corpus: OpenAlex/arXiv/S2 return sources
  *because* they are relevant, so a 3-reference check is the very top of the ranking
  and a 6 000-sentence academic corpus is the same top plus a long tail. It is the
  **ceiling** of the effect, for two reasons worth stating: the ranker is the same
  bi-encoder being evaluated, and an unlabelled true paraphrase sitting in the pool
  gets promoted straight to the top (`--examples` dumps the highest-scoring pairs so
  that contamination is visible rather than assumed).

The honest reading is that production lives *between* the two curves.

This is the *paraphrase pillar under corpus conditions*, not the whole product: it
skips verbatim matching, the relevance budget and reranking. It answers exactly one
question — how far does max-over-N move the operating point — and nothing more.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

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
class NearMiss:
    """A top-scoring (negative query, corpus sentence) pair — dumped for human eyes.

    Every one of these is a false positive *by construction*. If a human reading them
    finds real paraphrases, the pool is contaminated and the FPR is overstated: that is
    exactly what this list exists to expose.
    """
    score: float
    query: str
    corpus_sentence: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScaleReport:
    dataset: str
    model_key: str
    corpus_sizes: List[int]
    thresholds: List[float]
    results: List[ScaleResult] = field(default_factory=list)
    distractor_mode: str = "random"
    pool_size: int = 0
    pool_only: bool = False
    drop_above: float = 0.0
    dropped_near_duplicates: int = 0
    pool_datasets: List[str] = field(default_factory=list)
    near_misses: List[NearMiss] = field(default_factory=list)

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
                "distractor_mode": self.distractor_mode, "pool_size": self.pool_size,
                "pool_only": self.pool_only, "drop_above": self.drop_above,
                "dropped_near_duplicates": self.dropped_near_duplicates,
                "pool_datasets": list(self.pool_datasets),
                "corpus_sizes": self.corpus_sizes, "thresholds": self.thresholds,
                "results": [r.as_dict() for r in self.results],
                "near_misses": [m.as_dict() for m in self.near_misses]}


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
    pool_pairs: Sequence[PairCase] = (),
    pool_only: bool = False,
) -> tuple[List[str], List[str], List[str], List[str]]:
    """(negative_queries, positive_queries, positive_truths, distractors).

    `pool_pairs` (optional) contribute **distractors only** — never queries. They are
    how a retrieval-conditioned probe gets a pool deep enough to select from; drawing
    them from *other* datasets also lowers the chance that an unlabelled paraphrase of
    a query is sitting in the corpus.

    `pool_only=True` goes further and takes the corpus **entirely** from `pool_pairs`,
    so not one sentence of the query dataset is in it. That is the only construction in
    which "no true match exists" is guaranteed rather than assumed: within a single
    dataset, only a query's *labelled* partner can be excluded, and QQP in particular
    is full of unlabelled duplicates that a similarity ranking promotes straight to the
    top. The cost is that a cross-dataset corpus is topically further away than a real
    retrieved one, so it bounds the effect from below.
    """
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
    extra = list(pool_pairs)
    rng.shuffle(extra)
    for p in (extra if pool_only else list(pool) + extra):
        for text in (p.a, p.b):
            if len(distractors) >= max_corpus:
                break
            if text in seen or text in excluded:
                continue
            distractors.append(text)
            seen.add(text)
    return neg_q, pos_q, pos_truth, distractors


def retrieval_order(neg_sims: Any, pos_sims: Any = None) -> Any:
    """Pool indices ordered as a *retriever* would return them (ADR-0025).

    Rank each pool sentence by its best similarity to any sentence of the manuscript —
    the same signal OpenAlex/arXiv relevance stands in for. The corpus at size N is then
    the top N of that ranking, which is what a real check compares against: a small
    corpus is the head of the ranking, a large one is the head plus its tail.
    """
    import numpy as np

    best = neg_sims.max(axis=0)
    if pos_sims is not None and getattr(pos_sims, "size", 0):
        best = np.maximum(best, pos_sims.max(axis=0))
    return np.argsort(-best, kind="stable")


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
    distractor_mode: str = "random",
    pool_pairs: Sequence[PairCase] = (),
    pool_datasets: Sequence[str] = (),
    pool_only: bool = False,
    drop_above: float = 0.0,
    n_near_misses: int = 0,
) -> ScaleReport:
    """Measure FPR/recall vs corpus size. `embed(texts) -> (n, dim)` array.

    Everything is embedded once and sliced per corpus size, so a sweep costs one pass.

    `distractor_mode="retrieved"` orders the pool by similarity to the manuscript before
    slicing (see the module docstring); it needs a pool **larger** than the biggest
    corpus size to have anything to select, so pass `pool_pairs` from other datasets.
    """
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    if distractor_mode not in ("random", "retrieved"):
        raise ValueError(f"unknown distractor_mode {distractor_mode!r} (random | retrieved)")

    sizes = sorted({int(n) for n in corpus_sizes if n > 0})
    max_needed = max(sizes)
    # `random` needs exactly the largest corpus; `retrieved` wants every sentence it can
    # get, because the selection pressure *is* the measurement.
    pool_budget = max_needed if distractor_mode == "random" else max(max_needed, 10 ** 9)
    neg_q, pos_q, pos_truth, distractors = build_probe_with_truth(
        pairs, n_queries=n_queries, max_corpus=pool_budget, seed=seed,
        pool_pairs=pool_pairs, pool_only=pool_only)
    if not neg_q or not distractors:
        raise ValueError("not enough data to build a corpus-scale probe")

    neg_emb = np.asarray(embed(neg_q), dtype=np.float32)
    pos_emb = np.asarray(embed(pos_q), dtype=np.float32) if pos_q else None
    dis_emb = np.asarray(embed(distractors), dtype=np.float32)
    truth_emb = np.asarray(embed(pos_truth), dtype=np.float32) if pos_truth else None

    neg_sims_full = cosine_similarity(neg_emb, dis_emb)                       # (Q, D)
    pos_vs_dis = cosine_similarity(pos_emb, dis_emb) if pos_emb is not None else None

    # Sensitivity analysis for a same-dataset pool (ADR-0025). "No true match in the corpus"
    # is only enforced pairwise — a query's *labelled* partner is excluded, but a duplicate of
    # it living in some other pair is not, and QQP is full of those. Dropping every corpus
    # sentence within `drop_above` of any query removes the near-certain ones and turns an
    # unbounded "the FPR is contaminated" into a bound. It is still an upper bound: a genuine
    # paraphrase scoring 0.85 survives the cut.
    dropped = 0
    if drop_above:
        peak = neg_sims_full.max(axis=0)
        if pos_vs_dis is not None:
            peak = np.maximum(peak, pos_vs_dis.max(axis=0))
        keep = peak < drop_above
        dropped = int((~keep).sum())
        neg_sims_full = neg_sims_full[:, keep]
        if pos_vs_dis is not None:
            pos_vs_dis = pos_vs_dis[:, keep]
        dis_emb = dis_emb[keep]
        distractors = [t for t, k in zip(distractors, keep) if k]
        if not distractors:
            raise ValueError(f"drop_above={drop_above} removed every distractor")

    pool_size = len(distractors)
    if distractor_mode == "retrieved":
        order = retrieval_order(neg_sims_full, pos_vs_dis)
        neg_sims_full = neg_sims_full[:, order]
        if pos_vs_dis is not None:
            pos_vs_dis = pos_vs_dis[:, order]
        distractors = [distractors[i] for i in order]
    # A positive query's own truth sentence is always in the corpus, whatever its size.
    pos_vs_truth = (np.sum(pos_emb * truth_emb, axis=1) /
                    (np.linalg.norm(pos_emb, axis=1) * np.linalg.norm(truth_emb, axis=1) + 1e-12)
                    ) if pos_emb is not None else None

    report = ScaleReport(dataset=dataset, model_key=model_key,
                         corpus_sizes=sizes, thresholds=list(thresholds),
                         distractor_mode=distractor_mode, pool_size=pool_size, pool_only=pool_only,
                         drop_above=drop_above, dropped_near_duplicates=dropped,
                         pool_datasets=list(pool_datasets),
                         near_misses=_near_misses(neg_sims_full[:, :min(max_needed, pool_size)],
                                                  neg_q, distractors, n_near_misses))
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


def _near_misses(neg_sims: Any, neg_queries: Sequence[str], distractors: Sequence[str],
                 k: int) -> List[NearMiss]:
    """The k highest-scoring (negative query, corpus sentence) pairs, best pair per query.

    Best *per query* rather than globally, so one pathological query cannot fill the list
    and hide the rest. These are the flags the probe counts as false positives; reading
    them is how contamination gets caught instead of assumed.
    """
    if k <= 0 or neg_sims.size == 0:
        return []
    import numpy as np

    best_col = neg_sims.argmax(axis=1)
    best_val = neg_sims.max(axis=1)
    order = np.argsort(-best_val)[:k]
    return [NearMiss(score=round(float(best_val[i]), 4),
                     query=neg_queries[i],
                     corpus_sentence=distractors[int(best_col[i])])
            for i in order]


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

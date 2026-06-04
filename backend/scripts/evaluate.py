"""
P.R.I.S.M. — Macro Evaluation Harness
=======================================
Runs the three detection methods (TF-IDF Baseline, Math-Only, Hybrid PRISM)
across an expanded synthetic corpus of 14 documents ranging from 10 to 100
paragraphs, covering both single-author and multi-author ground-truth cases.

For each method the harness accumulates raw TP / FP / TN / FN counts across
all documents and derives Accuracy, Precision, Recall, F1, and a formatted
console Confusion Matrix ready for presentation copy-paste.

Usage:
    python scripts/evaluate.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from benchmark import tfidf_baseline, math_only, hybrid_prism

# Each pool holds 20 unique sentences so paragraphs drawn from it are varied
# enough for TF-IDF not to collapse on identical token sets.

_POOL_FORMAL = [
    "The implementation of distributed computing architectural paradigms exhibits localized optimization constraints regarding system execution matrix frameworks.",
    "It has been systematically observed by various researchers that semantic vector spaces demonstrate considerable vulnerability when exposed to non-linear noise fields.",
    "Therefore, the initialization parameters must be carefully calibrated to mitigate anomalous deviations within the latent clustering dimensional constructs.",
    "Comprehensive analysis of the algorithmic throughput indicates a statistically significant correlation between memory allocation boundaries and runtime latencies.",
    "In conclusion, the mathematical validation of the proposed sub-system relies heavily upon the uniform distribution of density-based reachability metrics.",
    "Furthermore, the empirical data gathered during the secondary phase substantiates our core hypothesis regarding structural load distribution frameworks.",
    "Subsequent evaluations of the processing nodes confirm that optimization remains uniform across all concurrent operational system channels.",
    "This formal methodology ensures that no external stylistic variances contaminate the integrity of our primary analytical pipeline vectors.",
    "Thus, the cross-validation metrics remain tightly aligned with the established benchmarks of our technical deployment specifications.",
    "Final observations indicate that scholastic document synthesis maintains an unyielding stylistic standard when authored by a single institutional entity.",
    "The proposed regularization scheme substantially diminishes overfitting phenomena observed within high-dimensional latent representation manifolds.",
    "Empirical corroboration of the theoretical model demands rigorous statistical treatment of each experimental variable within the controlled laboratory context.",
    "Asymptotic convergence of the iterative optimization procedure has been demonstrated under the imposed Lipschitz continuity constraints.",
    "The orthogonal decomposition methodology facilitates dimensionality reduction while preserving maximal variance across the principal feature subspace.",
    "Resultant spectral analysis confirms the hypothesis that inter-cluster boundary distances correlate inversely with local density gradient magnitudes.",
    "Methodological transparency necessitates the explicit enumeration of each preprocessing transformation applied to the raw observational dataset.",
    "Comparative benchmarking against established baseline architectures validates the superiority of the proposed density-aware clustering mechanism.",
    "The stochastic gradient descent optimizer was configured with an adaptive learning rate schedule to ensure stable convergence throughout training epochs.",
    "Ablation studies systematically isolate the contribution of each architectural component to the overall classification performance on held-out evaluation sets.",
    "Reproducibility of the experimental outcomes was verified by executing five independent randomized trials with distinct initialization seeds.",
]

_POOL_INFORMAL = [
    "We just built a simple script to handle this workflow fast and it runs cleanly without any extra boilerplate code.",
    "If you look at how the data flows through the pipe you can see right away where the bottleneck is slowing everything down.",
    "I decided to strip out the old database calls and swap them with an in-memory cache to make the server load instantly.",
    "Let's keep things straightforward for the demo because we don't need over-engineered solutions when a basic array map does the trick.",
    "We ran a few tests on our local machines and noticed that execution times dropped to nearly zero milliseconds after our patch.",
    "Honestly the whole setup took like ten minutes once we figured out the environment variables were missing from the config file.",
    "I pushed a quick fix to the main branch so just pull the latest and you should be good to go without any extra steps.",
    "The error was super obvious in hindsight but it took us two hours to track down because the stack trace pointed to the wrong line.",
    "We're going to refactor this whole section next sprint because right now it's basically held together with string and optimism.",
    "My personal opinion is that the old architecture was way too complicated for what we actually needed it to do.",
    "Just run the setup script and it'll handle everything for you, no manual configuration required at all.",
    "I added some debug prints so you can see exactly what's happening at each step if things go sideways again.",
    "We tested this on three different machines and it worked perfectly every single time with zero issues.",
    "The fix was literally a one-liner once we understood what was actually causing the race condition.",
    "Honestly we should have written tests for this from day one but here we are fixing it in production again.",
    "I refactored the whole thing over the weekend because the old version was impossible to read after six months away from the code.",
    "We're using a really simple pub-sub pattern here instead of the heavyweight event bus the previous team left behind.",
    "The new version boots up in about two seconds flat compared to the forty second cold start we had before.",
    "I know it looks hacky but it ships and we can clean it up properly once the deadline pressure is off.",
    "We decided to drop the external dependency entirely and just rewrite the thirty lines ourselves to keep the bundle small.",
]

_POOL_SCIENTIFIC = [
    "Neuroplasticity research demonstrates that repeated synaptic activation strengthens dendritic connectivity through long-term potentiation mechanisms in hippocampal tissue.",
    "The observed quantum decoherence timescales in room-temperature biological systems challenge conventional assumptions regarding coherent energy transfer in photosynthetic complexes.",
    "Genomic sequencing of the novel strain reveals seventeen previously uncharacterised open reading frames with putative enzymatic functionality awaiting experimental confirmation.",
    "Thermodynamic modelling of the stellar interior constrains the helium abundance fraction to within two percent of the predicted solar standard model value.",
    "The catalyst exhibited turnover frequencies three orders of magnitude higher than conventional palladium systems under identical temperature and pressure reaction conditions.",
    "Longitudinal cohort data spanning two decades demonstrate a statistically robust inverse relationship between dietary fibre intake and colorectal adenoma recurrence rates.",
    "Isotopic fractionation patterns preserved in the carbonate sediment record provide unambiguous evidence of an abrupt oceanographic transition at the Cretaceous boundary.",
    "Single-molecule fluorescence imaging resolves conformational dynamics of the ribosomal complex at sub-nanometre precision across the complete translation elongation cycle.",
    "The percolation threshold of the composite material shifts by 0.08 volume fraction when particle aspect ratios exceed the critical value of twelve.",
    "Density functional theory calculations predict a band gap reduction of 0.4 electronvolts upon substitutional doping of the host lattice with boron atoms.",
]

_POOL_BUSINESS = [
    "Q3 revenue grew by fourteen percent year-over-year driven primarily by strong performance in the enterprise software licensing segment across North American markets.",
    "The restructuring initiative is expected to yield annualised cost savings of approximately forty million dollars by the end of the next fiscal year.",
    "Customer acquisition costs declined for the third consecutive quarter as the shift toward organic search and referral channels gained momentum across all verticals.",
    "The board has approved a share buyback programme of up to two hundred million dollars to be executed over the next eighteen months.",
    "Churn rates in the SMB segment remain elevated and the customer success team has been expanded to address onboarding friction identified in exit surveys.",
    "Market penetration in the APAC region accelerated following the strategic partnership announcement and localised pricing adjustments implemented in the second quarter.",
    "Gross margin expansion of 180 basis points reflects improved supply chain discipline and the favourable renegotiation of key vendor contracts.",
    "The sales pipeline entering Q4 represents the strongest position in company history with a three-times increase in enterprise opportunities above the one-million-dollar threshold.",
    "Operating leverage improved materially as headcount growth was contained to eight percent while total revenue scaled by over twenty-two percent.",
    "The newly launched product tier has already captured seven percent of the addressable installed base within its first sixty days of general availability.",
]


def _make_paragraph(text: str) -> dict:
    return {"text": text}


def _cycle(pool: list, n: int) -> list:
    """Draw n paragraphs from a pool, cycling if n exceeds pool length."""
    return [_make_paragraph(pool[i % len(pool)]) for i in range(n)]


def _interleave(pool_a: list, pool_b: list, n: int) -> list:
    """
    Build a mixed-author document of n paragraphs by alternating between
    two pools in unequal blocks (3 from A, 2 from B) to produce realistic
    stylometric boundaries rather than a perfect paragraph-by-paragraph flip.
    """
    paras = []
    ia, ib = 0, 0
    block_pattern = [3, 2] 
    toggle = 0
    while len(paras) < n:
        block_size = block_pattern[toggle % 2]
        for j in range(block_size):
            if len(paras) >= n:
                break
            src = pool_a if toggle % 2 == 0 else pool_b
            offset = ia if toggle % 2 == 0 else ib
            paras.append(_make_paragraph(src[(offset + j) % len(src)]))
        if toggle % 2 == 0:
            ia += block_size
        else:
            ib += block_size
        toggle += 1
    return paras[:n]


# Size tiers:
#   XS  = 10 paragraphs
#   SM  = 20 paragraphs
#   MD  = 35 paragraphs
#   LG  = 60 paragraphs
#   XL  = 100 paragraphs

def build_corpus() -> list:
    corpus = [
        (
            "XS-01 | Short Mixed | Formal + Informal",
            _interleave(_POOL_FORMAL, _POOL_INFORMAL, 10),
            True,
        ),
        (
            "XS-02 | Short Clean | Formal Only",
            _cycle(_POOL_FORMAL, 10),
            False,
        ),
        (
            "XS-03 | Short Mixed | Scientific + Business",
            _interleave(_POOL_SCIENTIFIC, _POOL_BUSINESS, 10),
            True,
        ),
        (
            "SM-01 | Medium Mixed | Formal + Informal",
            _interleave(_POOL_FORMAL, _POOL_INFORMAL, 20),
            True,
        ),
        (
            "SM-02 | Medium Clean | Informal Only",
            _cycle(_POOL_INFORMAL, 20),
            False,
        ),
        (
            "SM-03 | Medium Mixed | Formal + Scientific",
            _interleave(_POOL_FORMAL, _POOL_SCIENTIFIC, 20),
            True,
        ),
        (
            "MD-01 | Standard Mixed | Formal + Informal",
            _interleave(_POOL_FORMAL, _POOL_INFORMAL, 35),
            True,
        ),
        (
            "MD-02 | Standard Clean | Scientific Only",
            _cycle(_POOL_SCIENTIFIC, 35),
            False,
        ),
        (
            "MD-03 | Standard Mixed | Scientific + Informal",
            _interleave(_POOL_SCIENTIFIC, _POOL_INFORMAL, 35),
            True,
        ),
        (
            "LG-01 | Long Mixed | Formal + Business",
            _interleave(_POOL_FORMAL, _POOL_BUSINESS, 60),
            True,
        ),
        (
            "LG-02 | Long Clean | Business Only",
            _cycle(_POOL_BUSINESS, 60),
            False,
        ),
        (
            "LG-03 | Long Mixed | Informal + Scientific",
            _interleave(_POOL_INFORMAL, _POOL_SCIENTIFIC, 60),
            True,
        ),
        (
            "XL-01 | Full Paper Mixed | Formal + Informal",
            _interleave(_POOL_FORMAL, _POOL_INFORMAL, 100),
            True,
        ),
        (
            "XL-02 | Full Paper Clean | Formal Only",
            _cycle(_POOL_FORMAL, 100),
            False,
        ),
    ]
    return corpus


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator != 0 else 0.0


def compute_metrics(tp: int, fp: int, tn: int, fn: int) -> dict:
    accuracy  = _safe_divide(tp + tn, tp + fp + tn + fn)
    precision = _safe_divide(tp, tp + fp)
    recall    = _safe_divide(tp, tp + fn)
    f1        = _safe_divide(2 * precision * recall, precision + recall)
    return {
        "accuracy":  accuracy,
        "precision": precision,
        "recall":    recall,
        "f1":        f1,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


W = 72  # console width


def _hr(char: str = "═") -> str:
    return char * W


def _banner(text: str) -> None:
    print(_hr())
    pad = (W - len(text) - 2) // 2
    print(f"{'':>{pad}} {text}")
    print(_hr())


def _section(text: str) -> None:
    print(f"\n{'─' * W}")
    print(f"  {text}")
    print(f"{'─' * W}")


def print_confusion_matrix(method_name: str, tp: int, fp: int, tn: int, fn: int) -> None:
    """
    Prints a labelled 2×2 Confusion Matrix aligned for terminal presentation.

    Layout (Actual as rows, Predicted as columns):

                         Predicted
                    Positive    Negative
    Actual  Positive  [ TP ]    [ FN ]
            Negative  [ FP ]    [ TN ]
    """
    col_w   = 12
    label_w = 18

    header_pad = " " * (label_w + 2)
    print(f"\n  ┌{'─' * (W - 4)}┐")
    print(f"  │  Confusion Matrix — {method_name:<{W - 25}}│")
    print(f"  ├{'─' * (W - 4)}┤")

    trailing_header = " " * (W - label_w - col_w * 2 - 8)
    print(f"  │{header_pad}{'Predicted (+)':^{col_w}}  {'Predicted (−)':^{col_w}}{trailing_header}│")
    print(f"  ├{'─' * (W - 4)}┤")

    tp_cell = f"TP = {tp:>4}"
    fn_cell = f"FN = {fn:>4}"
    row_label = f"{'Actual (+)':>{label_w}}"
    trailing_data = " " * (W - label_w - col_w * 2 - 11)
    print(f"  │  {row_label}   {tp_cell:^{col_w}}  {fn_cell:^{col_w}}{trailing_data}│")

    fp_cell = f"FP = {fp:>4}"
    tn_cell = f"TN = {tn:>4}"
    row_label = f"{'Actual (−)':>{label_w}}"
    print(f"  │  {row_label}   {fp_cell:^{col_w}}  {tn_cell:^{col_w}}{trailing_data}│")

    print(f"  └{'─' * (W - 4)}┘")


def print_metrics_block(metrics: dict) -> None:
    tp, fp, tn, fn = metrics["tp"], metrics["fp"], metrics["tn"], metrics["fn"]
    total = tp + fp + tn + fn

    print(f"\n  {'Metric':<18}  {'Value':>10}   {'Notes'}")
    print(f"  {'─' * 18}  {'─' * 10}   {'─' * 26}")
    print(f"  {'Accuracy':<18}  {metrics['accuracy']:>9.1%}   ({tp + tn}/{total} correct)")
    print(f"  {'Precision':<18}  {metrics['precision']:>9.1%}   (of predicted +, how many real +)")
    print(f"  {'Recall':<18}  {metrics['recall']:>9.1%}   (of actual +, how many caught)")
    print(f"  {'F1 Score':<18}  {metrics['f1']:>9.4f}   (harmonic mean of P & R)")
    print(f"\n  Raw counts →  TP={tp}  FP={fp}  TN={tn}  FN={fn}  (n={total} docs)")


def print_per_document_row(
    label: str,
    ground_truth: bool,
    result: dict,
    elapsed_ms: int,
) -> None:
    detected = result.get("detected", False)
    correct  = detected == ground_truth

    gt_tag   = "POS" if ground_truth else "NEG"
    pred_tag = "POS" if detected else "NEG"

    if correct and ground_truth:
        outcome = "TP ✓"
    elif correct and not ground_truth:
        outcome = "TN ✓"
    elif not correct and ground_truth:
        outcome = "FN ✗"
    else:
        outcome = "FP ✗"

    label_trunc = label[:36]
    print(
        f"  {label_trunc:<38}  GT:{gt_tag}  Pred:{pred_tag}  "
        f"{outcome:<6}  {elapsed_ms:>4}ms"
    )


METHODS = [
    ("TF-IDF Baseline",    tfidf_baseline),
    ("Math-Only (HDBSCAN)", math_only),
    ("Hybrid PRISM (Ours)", hybrid_prism),
]


def evaluate_corpus(corpus: list) -> dict:
    """
    Run all three methods over every document in the corpus.

    Returns a nested dict:
        { method_name: { "counters": {tp,fp,tn,fn}, "per_doc": [...] } }
    """
    state = {
        name: {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "per_doc": [], "total_ms": 0}
        for name, _ in METHODS
    }

    n_docs = len(corpus)

    for doc_idx, (label, paragraphs, ground_truth) in enumerate(corpus, start=1):
        _section(f"Document {doc_idx}/{n_docs}  ·  {label}  ·  {len(paragraphs)} paragraphs")
        print(f"  Ground truth: {'MULTI-AUTHOR (positive)' if ground_truth else 'SINGLE-AUTHOR (negative)'}\n")

        for method_name, method_fn in METHODS:
            t0 = time.perf_counter()
            try:
                result = method_fn(paragraphs)
            except Exception as exc:
                result = {"detected": False, "method": method_name, "error": str(exc)}
            elapsed_ms = round((time.perf_counter() - t0) * 1000)

            detected = result.get("detected", False)
            s = state[method_name]
            s["total_ms"] += elapsed_ms

            if detected and ground_truth:
                s["tp"] += 1
            elif detected and not ground_truth:
                s["fp"] += 1
            elif not detected and not ground_truth:
                s["tn"] += 1
            else:
                s["fn"] += 1

            s["per_doc"].append({
                "label":       label,
                "ground_truth": ground_truth,
                "detected":    detected,
                "elapsed_ms":  elapsed_ms,
            })

            print_per_document_row(label, ground_truth, result, elapsed_ms)

    return state


def print_final_report(state: dict) -> None:
    _banner("P.R.I.S.M. — MACRO EVALUATION REPORT")

    all_metrics = {}
    for method_name, _ in METHODS:
        s = state[method_name]
        m = compute_metrics(s["tp"], s["fp"], s["tn"], s["fn"])
        all_metrics[method_name] = m

    for method_name, _ in METHODS:
        s = state[method_name]
        m = all_metrics[method_name]

        print(f"\n\n  ▌ {method_name}")
        print(f"  {'─' * (W - 4)}")
        print_metrics_block(m)
        print_confusion_matrix(method_name, m["tp"], m["fp"], m["tn"], m["fn"])
        avg_ms = s["total_ms"] // max(len(s["per_doc"]), 1)
        print(f"\n  Avg inference time: {avg_ms}ms / document")

    print(f"\n\n{_hr()}")
    print(f"  COMPARATIVE SUMMARY  ({sum(len(s['per_doc']) for _, s in state.items()) // len(METHODS)} documents evaluated)")
    print(_hr())

    col = 13
    header = f"  {'Method':<25}  {'Accuracy':>{col}}  {'Precision':>{col}}  {'Recall':>{col}}  {'F1 Score':>{col}}"
    print(header)
    print(f"  {'─' * 25}  {'─' * col}  {'─' * col}  {'─' * col}  {'─' * col}")

    for method_name, _ in METHODS:
        m = all_metrics[method_name]
        print(
            f"  {method_name:<25}  "
            f"{m['accuracy']:>{col}.1%}  "
            f"{m['precision']:>{col}.1%}  "
            f"{m['recall']:>{col}.1%}  "
            f"{m['f1']:>{col}.4f}"
        )

    best_name = max(all_metrics, key=lambda k: all_metrics[k]["f1"])
    best_f1   = all_metrics[best_name]["f1"]
    print(f"\n  ★  Best F1: {best_name}  →  {best_f1:.4f}")

    print(f"\n{_hr()}")
    print(f"  Evaluation complete.  Results above are ready for presentation.")
    print(_hr())


def main() -> None:
    _banner("P.R.I.S.M. — MACRO EVALUATION HARNESS  v1.0")
    print(f"\n  Importing detection methods from benchmark.py")
    print(f"  Methods under test: {', '.join(name for name, _ in METHODS)}")

    corpus = build_corpus()

    pos_docs = sum(1 for _, _, gt in corpus if gt)
    neg_docs = sum(1 for _, _, gt in corpus if not gt)
    sizes    = [len(p) for _, p, _ in corpus]

    print(f"\n  Corpus summary:")
    print(f"    Total documents   : {len(corpus)}")
    print(f"    Positive (multi)  : {pos_docs}")
    print(f"    Negative (single) : {neg_docs}")
    print(f"    Paragraph range   : {min(sizes)} – {max(sizes)}")
    print(f"    Total paragraphs  : {sum(sizes)}")

    print(f"\n  Beginning evaluation …\n")

    state = evaluate_corpus(corpus)
    print_final_report(state)


if __name__ == "__main__":
    main()
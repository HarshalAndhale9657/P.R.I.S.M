"""
P.R.I.S.M. — Originality Matcher Evaluation Harness
===================================================
Runs the matcher over a controlled, labelled benchmark (scripts/eval_data.json) and
reports passage-level precision / recall / F1, **recall by type x difficulty**, and —
most importantly for a self-check tool — the **false-positive rate per negative
stratum** (same-topic, boilerplate, ESL, shared-terminology, unrelated).

This is a *controlled synthetic* benchmark (not real-world prevalence): each passage is
deliberately authored. It is a regression + failure-mode gauge, not proof of accuracy.
Exits non-zero if quality regresses past the gates below.

    python scripts/eval_matcher.py            # from backend/
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `import services...`

from services.plagiarism_matcher import PlagiarismMatcher, SourceDoc

# ── CI gates ──────────────────────────────────────────────────────────────────
MIN_RECALL = 0.70          # overall positive recall
MAX_FPR = 0.15             # overall false-positive rate on originals
MAX_STRATUM_FPR = 0.34     # no single negative stratum may exceed this

_DATA = json.loads((Path(__file__).with_name("eval_data.json")).read_text(encoding="utf-8"))
SOURCES = [SourceDoc(id=s["id"], name=s["name"], text=s["text"]) for s in _DATA["sources"]]
CASES = _DATA["cases"]


def _assemble(cases):
    sep = "\n\n"
    parts, ranges, pos = [], [], 0
    for c in cases:
        t = c["text"]
        parts.append(t)
        ranges.append((pos, pos + len(t)))
        pos += len(t) + len(sep)
        parts.append(sep)
    return "".join(parts), ranges


def _overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def _rate(num, den):
    return (num / den) if den else 0.0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
    except Exception:
        pass

    matcher = PlagiarismMatcher()
    doc_text, ranges = _assemble(CASES)
    result = matcher.check(doc_text, SOURCES)
    matches = result["matches"]

    if not result.get("paraphrase_enabled"):
        print("NOTE: paraphrase model unavailable - paraphrase/translated recall will be understated.\n")

    # ── Score each case: is it flagged (>=30% covered by any match)? ──
    for i, c in enumerate(CASES):
        c0, c1 = ranges[i]
        clen = max(c1 - c0, 1)
        covered, hit_types = 0, set()
        for m in matches:
            ov = _overlap(c0, c1, m["doc_start"], m["doc_end"])
            if ov > 0:
                covered += ov
                hit_types.add(m["match_type"])
        c["_frac"] = min(covered / clen, 1.0)
        c["_flagged"] = c["_frac"] >= 0.30
        c["_types"] = hit_types

    pos = [c for c in CASES if c["kind"] == "positive"]
    neg = [c for c in CASES if c["kind"] == "negative"]
    tp = sum(1 for c in pos if c["_flagged"])
    fn = len(pos) - tp
    fp = sum(1 for c in neg if c["_flagged"])
    tn = len(neg) - fp

    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = _rate(2 * precision * recall, precision + recall)
    specificity = _rate(tn, tn + fp)
    fpr = _rate(fp, fp + tn)

    print("=" * 78)
    print(f"PRISM Matcher Evaluation  -  {len(pos)} positives, {len(neg)} negatives")
    print("=" * 78)
    print(f"Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}  "
          f"Specificity={specificity:.3f}  FalsePositiveRate={fpr:.3f}")
    print(f"Confusion: TP={tp} FN={fn} FP={fp} TN={tn}")

    # ── Recall by type x difficulty ──
    print("\nRecall by type x difficulty (positives):")
    grid = defaultdict(lambda: [0, 0])  # (type,difficulty) -> [hit, total]
    for c in pos:
        key = (c["type"], c.get("difficulty", "-"))
        grid[key][1] += 1
        if c["_flagged"]:
            grid[key][0] += 1
    for key in sorted(grid):
        hit, total = grid[key]
        print(f"  {key[0]:<11}{key[1]:<8} {hit}/{total}  recall={_rate(hit, total):.2f}")

    # ── FPR by negative stratum (the safety-critical view) ──
    print("\nFalse-positive rate by stratum (negatives):")
    strat = defaultdict(lambda: [0, 0])  # stratum -> [flagged, total]
    for c in neg:
        s = c.get("stratum", "-")
        strat[s][1] += 1
        if c["_flagged"]:
            strat[s][0] += 1
    stratum_fprs = {}
    for s in sorted(strat):
        flagged, total = strat[s]
        rate = _rate(flagged, total)
        stratum_fprs[s] = rate
        print(f"  {s:<20} {flagged}/{total} flagged   FPR={rate:.2f}")

    # ── Misclassifications (actionable) ──
    misses = [c for c in pos if not c["_flagged"]]
    falsepos = [c for c in neg if c["_flagged"]]
    if misses:
        print("\nMissed positives (false negatives):")
        for c in misses:
            print(f"  [{c['type']}/{c.get('difficulty','-')}] {c['text'][:64]}...")
    if falsepos:
        print("\nFlagged originals (false positives):")
        for c in falsepos:
            print(f"  [{c.get('stratum','-')}] {c['text'][:64]}...  ({','.join(c['_types'])})")

    # ── Gates ──
    worst_stratum = max(stratum_fprs.values(), default=0.0)
    ok = (recall >= MIN_RECALL) and (fpr <= MAX_FPR) and (worst_stratum <= MAX_STRATUM_FPR)
    print("\n" + "-" * 78)
    print(f"Gates: recall>={MIN_RECALL}  FPR<={MAX_FPR}  per-stratum FPR<={MAX_STRATUM_FPR}  "
          f"->  {'PASS' if ok else 'FAIL'}")

    (Path(__file__).with_name("eval_matcher_results.json")).write_text(json.dumps({
        "n_positives": len(pos), "n_negatives": len(neg),
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "specificity": round(specificity, 4), "false_positive_rate": round(fpr, 4),
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall_by_group": {f"{k[0]}/{k[1]}": {"hit": v[0], "total": v[1]} for k, v in grid.items()},
        "fpr_by_stratum": {k: round(v, 4) for k, v in stratum_fprs.items()},
        "paraphrase_enabled": result.get("paraphrase_enabled"),
        "gates_pass": ok,
    }, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

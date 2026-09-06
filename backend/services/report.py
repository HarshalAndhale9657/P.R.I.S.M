"""
P.R.I.S.M. — Submission-risk report and before/after re-check (W10, ADR-0032)
=============================================================================
Two pure functions over a finished result — no model, no I/O, fully deterministic:

* ``build_report`` turns the numbers into a **risk band with its reason**, a
  **checklist** of the fixes the triage found, standing **AI-use disclosure**
  guidance, and the **honest footer** every export must carry. The band never says
  "pass" or "fail": it says whether there is something to fix, something to look at,
  or nothing flagged *against the sources that were checked* — which is the only
  claim the coverage supports (LAUNCH_PLAN §11, "reduces risk, not a guaranteed pass").
* ``compare`` is the re-check: the same manuscript after edits, against the previous
  result. Matches are keyed by what they matched *against* (type, source, source
  excerpt), not by where they sat in the document — the author moved things, and a
  resolved flag is one whose source passage no longer has a counterpart. The output
  is counts and short examples, never a verdict.

The AI-risk band the plan mentions is **not** here: the AI-text detector is deferred
(ADR-0016), so the report says so rather than printing a number nobody measured.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_WS = re.compile(r"\s+")

BANDS = {
    "act": ("Fix before submitting",
            "At least one flag is a word-for-word or close-paraphrase match with no citation nearby."),
    "look": ("Worth a look",
             "Nothing needs fixing outright, but some passages are cited paraphrases or inconclusive matches you "
             "should read side by side with the source."),
    "clear": ("Nothing flagged",
              "No passage matched the sources that were checked. That is a statement about these sources, not "
              "about every source that exists."),
}

DISCLOSURE = (
    "Many journals now ask authors to state whether and how AI tools were used (for example in drafting, "
    "editing, translation or code). This checker does not detect AI-written text and makes no claim about it. "
    "If you used such tools, check the journal's policy and disclose in the manner it asks — usually a short "
    "statement in the methods or acknowledgements naming the tool and what it was used for. Not disclosing when "
    "a policy requires it is a compliance problem regardless of what any checker reports."
)

FOOTER = (
    "This report reduces the risk of an avoidable similarity problem; it is not a guarantee of passing any "
    "journal's or institution's check, which may compare against sources this check could not see. It is a "
    "self-check aid, not a determination of misconduct."
)


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip().casefold()


def _key(m: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(m.get("match_type", "")), str(m.get("source_id", "")), _norm(m.get("source_excerpt", ""))[:300])


def build_report(
    *,
    overall: Dict[str, Any],
    triage_summary: Optional[Dict[str, Any]],
    matches: Sequence[Dict[str, Any]],
    coverage: str,
) -> Dict[str, Any]:
    ts = triage_summary or {}
    needs_action = int(ts.get("needs_action", 0) or 0)
    items = list(ts.get("action_items") or [])
    review_count = int(overall.get("review_count", 0) or 0)
    p3 = sum(int(a.get("count", 0)) for a in items if int(a.get("priority", 9)) == 3)

    if needs_action > 0:
        band = "act"
    elif p3 > 0 or review_count > 0:
        band = "look"
    else:
        band = "clear"
    label, reason = BANDS[band]

    checklist: List[Dict[str, Any]] = [
        {"kind": "flag", "type": a.get("type"), "label": a.get("label"), "count": int(a.get("count", 0)),
         "priority": int(a.get("priority", 9))}
        for a in sorted(items, key=lambda a: (int(a.get("priority", 9)), -int(a.get("count", 0))))
    ]
    checklist.append({"kind": "standing", "type": "references", "priority": 3, "count": 1,
                      "label": "Confirm every source you drew on appears in your reference list."})
    checklist.append({"kind": "standing", "type": "disclosure", "priority": 4, "count": 1,
                      "label": "Add an AI-use disclosure if the journal's policy asks for one."})

    return {
        "band": band,
        "label": label,
        "reason": reason,
        "needs_action": needs_action,
        "review_count": review_count,
        "confident_pct": float(overall.get("confident_pct", 0.0) or 0.0),
        "similarity_pct": float(overall.get("similarity_pct", 0.0) or 0.0),
        "checklist": checklist,
        "disclosure": DISCLOSURE,
        "ai_text_detection": "not performed — deferred until it can be measured on a real ESL set (ADR-0016)",
        "footer": FOOTER,
        "coverage": coverage,
    }


def _snapshot(result: Dict[str, Any]) -> Dict[str, Any]:
    ov = result.get("overall") or {}
    ts = result.get("triage_summary") or {}
    return {
        "similarity_pct": float(ov.get("similarity_pct", 0.0) or 0.0),
        "confident_pct": float(ov.get("confident_pct", 0.0) or 0.0),
        "review_count": int(ov.get("review_count", 0) or 0),
        "match_count": int(ov.get("match_count", 0) or 0),
        "needs_action": int(ts.get("needs_action", 0) or 0),
        "band": (result.get("report") or {}).get("band"),
    }


def compare(previous: Dict[str, Any], current: Dict[str, Any], *, previous_job_id: Optional[str] = None,
            examples: int = 5) -> Dict[str, Any]:
    """Before/after over the same manuscript. Keys by what was matched against, not by position."""
    prev = {_key(m): m for m in (previous.get("matches") or [])}
    cur = {_key(m): m for m in (current.get("matches") or [])}
    resolved = [prev[k] for k in prev.keys() - cur.keys()]
    new = [cur[k] for k in cur.keys() - prev.keys()]
    remaining = [cur[k] for k in cur.keys() & prev.keys()]

    def brief(ms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ms = sorted(ms, key=lambda m: ((m.get("triage") or {}).get("priority", 9), -float(m.get("similarity", 0))))
        return [{"match_type": m.get("match_type"), "source_name": m.get("source_name"),
                 "source_excerpt": (m.get("source_excerpt") or "")[:120],
                 "type": (m.get("triage") or {}).get("type")} for m in ms[:examples]]

    before, after = _snapshot(previous), _snapshot(current)
    same_doc = _norm(previous.get("filename", "")) == _norm(current.get("filename", ""))
    return {
        "previous_job_id": previous_job_id,
        "same_filename": same_doc,
        "before": before,
        "after": after,
        "delta": {k: round(after[k] - before[k], 2) for k in ("similarity_pct", "confident_pct", "review_count",
                                                                "match_count", "needs_action")},
        "resolved": len(resolved),
        "new": len(new),
        "remaining": len(remaining),
        "resolved_examples": brief(resolved),
        "new_examples": brief(new),
        "method": "A flag counts as resolved when the source passage it matched no longer has a counterpart in "
                  "your document; moving a passage does not resolve it. Counts, not a verdict.",
    }


__all__ = ["build_report", "compare", "BANDS", "DISCLOSURE", "FOOTER"]

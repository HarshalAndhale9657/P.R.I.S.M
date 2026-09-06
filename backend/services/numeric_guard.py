"""
P.R.I.S.M. — Numeric guard: same shape, different figures (ADR-0026)
====================================================================
ADR-0025 measured what survives de-duplication in the corpus probe. The residual
false positives are not topic drift — they are **template text with different facts
in it**. The canonical pair, at cosine **0.877**:

    "The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96 percent, at 929.06."
    "The broader Standard & Poor's 500 Index gave up 11.91 points, or 1.19 percent, at 986.60."

Opposite direction, different figures, same skeleton. No cosine threshold separates
that from a real paraphrase — the sentences genuinely *are* near-identical in form —
so it needs a second, orthogonal signal.

The one this module provides is deliberately the smallest that the measurement
supported: **two sentences that state numbers and share essentially none of them**.
Measured on public data at the 0.78 cutoff (`eval/results/numeric_*.json`), that catches
24–72% of the non-paraphrase pairs above the cutoff while softening 2–10% of the true
ones, and is silent on PAWS, whose negatives keep every number. The gate is where the
catch/cost ratio *peaks* on each dataset independently — see `DEFAULT_GATE`.

What it does **not** do, by construction: it never hides a match, never touches the
reporting floor, and only ever moves one band, `confident → review` (ADR-0017's safe
direction). It is silent on verbatim matches — exact text has identical numbers by
definition — and on translated ones, where decimal separators and numerals legitimately
differ. So its worst case is asking the author to look at something themselves.

**Known limits**, because a signal's bounds belong next to it: digits and small number
words only (no "15.8 billion" vs "15 800 million" arithmetic, no date normalisation),
and multiset overlap ignores the *role* a number plays.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Small number words, so a paraphrase writing "five" for "5" is not a disagreement.
# Anything larger is left alone: "billion" is a multiplier, not a value, and guessing at
# it would invent a fact the sentence did not state.
_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")     # 1,653.62 · 15.8 · 2016 · 0.96
_ALPHA_RE = re.compile(r"[a-z]+")


def numbers_in(text: str) -> List[float]:
    """Every number the text states, as floats.

    Duplicates are kept: a sentence quoting 5% twice makes the claim twice, and
    collapsing that would let one shared figure vouch for a whole template.
    """
    if not text:
        return []
    out: List[float] = []
    for raw in _NUMBER_RE.findall(text):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:                          # malformed runs like "1,2,3"
            continue
    for word in _ALPHA_RE.findall(text.lower()):
        if word in _WORD_NUMBERS:
            out.append(float(_WORD_NUMBERS[word]))
    return out


def agreement(a: str, b: str) -> Optional[float]:
    """Multiset Jaccard overlap of the two texts' numbers, or None if inapplicable.

    `None` — not 0.0 and not 1.0 — when either side states no number: the signal is
    silent there, and silence must never be readable as evidence either way.
    """
    na, nb = numbers_in(a), numbers_in(b)
    if not na or not nb:
        return None
    pool = list(nb)
    shared = 0
    for value in na:
        for i, other in enumerate(pool):
            if value == other:
                shared += 1
                pool.pop(i)
                break
    union = len(na) + len(nb) - shared
    return round(shared / union, 4) if union else 1.0


#: Agreement at or below which the two texts are treated as stating different facts.
#: **Measured, not chosen** (`eval/results/numeric_*.json`): the ratio of negatives caught
#: to positives softened *peaks here independently* on MRPC (2.91x) and QQP (3.15x), and
#: 0.20 sits on STS-B's plateau (72.4% caught for 2.0% softened). Above it the ratio falls
#: on two of the three; below it, pairs that share only a number belonging to a **name**
#: — "the S&P 500 Index", "a Boeing 747" — read as agreeing when no fact is shared at all.
DEFAULT_GATE = 0.20


def conflicts(a: str, b: str, gate: float = DEFAULT_GATE) -> bool:
    """True when both texts state numbers and share at most `gate` of them.

    Partial overlap is normal in genuine paraphrase, so the gate is deliberately near
    zero: it fires when the two sentences share essentially no figure, not merely when
    one differs.
    """
    agreed = agreement(a, b)
    return agreed is not None and agreed <= gate

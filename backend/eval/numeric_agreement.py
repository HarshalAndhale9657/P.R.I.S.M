"""
P.R.I.S.M. — Eval view of the numeric guard (ADR-0025 finding 3 → ADR-0026)
===========================================================================
The signal itself lives in `services/numeric_guard.py`, because it ships. This module
is the *evaluation* side of it: one import, so the measured thing and the shipped thing
can never drift apart, plus the coverage helper the runner needs.

Run the measurement with `python -m eval.run_numeric mrpc stsb qqp paws`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.numeric_guard import agreement, conflicts, numbers_in  # noqa: E402,F401

__all__ = ["agreement", "conflicts", "numbers_in", "divergence", "applicable"]


def divergence(a: str, b: str) -> Optional[float]:
    """1 - agreement, or None where the signal does not apply."""
    agreed = agreement(a, b)
    return None if agreed is None else round(1.0 - agreed, 4)


def applicable(pairs: Sequence) -> List[int]:
    """Indices of pairs where both sides state a number — the signal's own coverage.

    Reported alongside every number derived from it: a signal that fires on 10% of
    pairs must never be quoted as if it fired on all of them.
    """
    return [i for i, p in enumerate(pairs) if numbers_in(p.a) and numbers_in(p.b)]

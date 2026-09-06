"""
P.R.I.S.M. — Flag triage (W8, ADR-0022)
========================================
Classify each match by the *honest fix it needs*, from deterministic, auditable
signals — never from a model, never by rewriting anything.

    signals   quoted?  cited nearby?  confidence band  match type  common phrase?
    ──────►   type + priority + plain-language guidance

Types (priority 1 = act first):
  1 verbatim_uncited          copied word-for-word, no citation, not quoted
  1 paraphrase_uncited        confident paraphrase/translation, no citation
  2 verbatim_cited_unquoted   cited, but copied without quotation marks
  2 quoted_uncited            quotation marks, but no citation nearby
  3 paraphrase_cited          cited paraphrase — fine if genuinely your own words
  3 needs_review              inconclusive similarity (ADR-0017 review band)
  4 common_phrase             boilerplate / standard phrasing — usually no action
  5 quoted_cited              properly attributed quotation

Guidance is coaching toward the legitimate fix (quote + cite, add a reference,
restate in your own words *with* the citation). It never suggests changing text to
lower a score without attribution — that would be evasion (ADR-0014).

Limits, stated plainly: citation detection is pattern-based (numeric [12], author-
year (Smith et al., 2020), narrative Smith (2020)); a citation elsewhere in the
paper is not seen; self-reuse is not detectable without the author's prior work.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

# ── Citation patterns ─────────────────────────────────────────────────────────
_CITE_NUMERIC = re.compile(r"\[\s*\d{1,3}(?:\s*[,–\-]\s*\d{1,3})*\s*\]")
_CITE_AUTHOR_YEAR = re.compile(
    r"\((?:[A-Z][\w'’\-]+(?:\s+(?:et\s+al\.?|and|&)\s*[A-Z]?[\w'’\-]*)*,?\s*(?:\d{4}[a-z]?|n\.d\.)"
    r"(?:\s*;\s*[A-Z][\w'’\-]+(?:\s+(?:et\s+al\.?|and|&)\s*[A-Z]?[\w'’\-]*)*,?\s*(?:\d{4}[a-z]?|n\.d\.))*(?:,\s*p+\.\s*\d+)?)\)"
)
_CITE_NARRATIVE = re.compile(r"\b[A-Z][\w'’\-]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][\w'’\-]+|&\s+[A-Z][\w'’\-]+))?\s*\(\d{4}[a-z]?\)")
_CITE_SUPERSCRIPT = re.compile(r"[¹²³⁰-⁹]+")

_OPEN_QUOTES = "\"“‘'«‹„"
_CLOSE_QUOTES = "\"”’'»›“"
_QUOTE_WINDOW = 4          # chars around the span to look for quotation marks

_STOPWORDS = frozenset(("a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for", "with",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "we", "our", "they", "their", "he", "she", "his", "her", "you", "your", "i", "my", "which", "who", "whom",
    "whose", "what", "when", "where", "why", "how", "all", "any", "each", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
    "should", "now", "has", "have", "had", "do", "does", "did", "into", "over", "under", "between", "about",
    "after", "before", "during", "also", "may", "might", "must", "shall"))
_COMMON_PHRASE_MAX_WORDS = 14
_COMMON_PHRASE_STOPWORD_RATIO = 0.55
_WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)


@dataclass
class Signals:
    quoted: bool = False
    cited: bool = False
    citation_markers: List[str] = field(default_factory=list)
    shared_by_sources: int = 1        # how many distinct sources contain this exact text
    stopword_ratio: float = 0.0
    words: int = 0
    numeric_conflict: bool = False    # states numbers, shares none with the source (ADR-0026)


@dataclass(frozen=True)
class Rule:
    type: str
    priority: int
    label: str
    what: str
    fix: str


RULES: Dict[str, Rule] = {
    "verbatim_uncited": Rule(
        "verbatim_uncited", 1, "Word-for-word, not cited",
        "This passage matches a source word-for-word and there is no citation nearby and no quotation marks.",
        "Either put it in quotation marks and cite the source, or restate the idea in your own words and cite the source. Do not just change a few words — that is still copying.",
    ),
    "paraphrase_uncited": Rule(
        "paraphrase_uncited", 1, "Close paraphrase, no citation",
        "This passage closely restates a source and no citation was found nearby.",
        "Add a citation to the source. If the wording tracks the original closely, rewrite it from your own understanding — with the citation kept.",
    ),
    "verbatim_cited_unquoted": Rule(
        "verbatim_cited_unquoted", 2, "Cited, but not quoted",
        "The source is cited nearby, but the text is copied word-for-word without quotation marks.",
        "If you want the exact words, put them in quotation marks (check your journal's limit on quotation length). Otherwise restate them in your own words and keep the citation.",
    ),
    "quoted_uncited": Rule(
        "quoted_uncited", 2, "Quoted, no citation",
        "The passage is in quotation marks, but no citation was found nearby.",
        "Add the citation right after the quotation and make sure the source is in your reference list.",
    ),
    "paraphrase_cited": Rule(
        "paraphrase_cited", 3, "Cited paraphrase",
        "This passage restates a cited source. That is normal scholarly practice if the words are genuinely yours.",
        "Compare it with the source: if sentence structure and phrasing mirror the original, rework it in your own words. Keep the citation.",
    ),
    "needs_review": Rule(
        "needs_review", 3, "Needs your review",
        "Similarity is in the inconclusive band: shared terminology or standard phrasing can look like this by coincidence.",
        "Read both side by side. If you did draw on this source, cite it. If not, no change is needed.",
    ),
    "common_phrase": Rule(
        "common_phrase", 4, "Common phrasing",
        "A short, formulaic phrase that appears in several sources or is mostly function words — typical boilerplate.",
        "Usually no action. If it is a definition or a methods statement copied from one specific source, cite it.",
    ),
    "quoted_cited": Rule(
        "quoted_cited", 5, "Attributed quotation",
        "The passage is quoted and cited — properly attributed.",
        "Nothing to fix. Check the journal's limit on quotation length if the quotation is long.",
    ),
}


# ── Signal extraction ─────────────────────────────────────────────────────────

def find_citations(text: str) -> List[str]:
    found: List[str] = []
    for rx in (_CITE_NUMERIC, _CITE_AUTHOR_YEAR, _CITE_NARRATIVE, _CITE_SUPERSCRIPT):
        found.extend(m.group(0).strip() for m in rx.finditer(text or ""))
    # de-duplicate, keep order
    seen, out = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def is_quoted(doc_text: str, start: int, end: int) -> bool:
    """Quotation marks immediately around the span (or as its first/last character)."""
    before = doc_text[max(0, start - _QUOTE_WINDOW):start]
    after = doc_text[end:end + _QUOTE_WINDOW]
    span = doc_text[start:end]
    opens = any(c in _OPEN_QUOTES for c in before) or (span[:1] in _OPEN_QUOTES if span else False)
    closes = any(c in _CLOSE_QUOTES for c in after) or (span[-1:] in _CLOSE_QUOTES if span else False)
    return opens and closes


def stopword_ratio(text: str) -> float:
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    return (sum(1 for w in words if w in _STOPWORDS) / len(words)) if words else 0.0


def _norm(text: str) -> str:
    return " ".join(_WORD_RE.findall((text or "").casefold()))


def _paragraph_text(doc_text: str, paragraphs: Sequence[Dict[str, Any]], m: Dict[str, Any]) -> str:
    """Text of the paragraph containing the match, else a ±300-char window (citations sit near the sentence)."""
    pi = m.get("paragraph_index")
    if pi is not None:
        for p in paragraphs:
            if p.get("index") == pi:
                if "text" in p:
                    return p["text"]
                return doc_text[p["start"]:p["end"]]
    return doc_text[max(0, m["doc_start"] - 300):m["doc_end"] + 300]


def collect_signals(doc_text: str, paragraphs: Sequence[Dict[str, Any]], m: Dict[str, Any],
                    normalized_sources: Dict[str, str]) -> Signals:
    s = Signals()
    excerpt = m.get("doc_excerpt") or doc_text[m["doc_start"]:m["doc_end"]]
    s.words = len(_WORD_RE.findall(excerpt))
    s.stopword_ratio = round(stopword_ratio(excerpt), 3)
    s.numeric_conflict = bool(m.get("numeric_conflict"))
    s.quoted = is_quoted(doc_text, m["doc_start"], m["doc_end"])
    context = _paragraph_text(doc_text, paragraphs, m)
    s.citation_markers = find_citations(context)
    s.cited = bool(s.citation_markers)
    if m.get("match_type") == "verbatim" and s.words <= 40 and normalized_sources:
        needle = _norm(m.get("source_excerpt") or excerpt)
        if needle:
            s.shared_by_sources = sum(1 for t in normalized_sources.values() if needle in t) or 1
    return s


# ── Classification ────────────────────────────────────────────────────────────

def classify(m: Dict[str, Any], s: Signals) -> Rule:
    mtype = m.get("match_type")
    if mtype == "verbatim":
        if s.shared_by_sources >= 2 or (s.words <= _COMMON_PHRASE_MAX_WORDS and s.stopword_ratio >= _COMMON_PHRASE_STOPWORD_RATIO):
            return RULES["common_phrase"]
        if s.quoted and s.cited:
            return RULES["quoted_cited"]
        if s.quoted:
            return RULES["quoted_uncited"]
        if s.cited:
            return RULES["verbatim_cited_unquoted"]
        return RULES["verbatim_uncited"]
    # paraphrase / translated
    if m.get("confidence") == "review":
        return RULES["needs_review"]
    if s.quoted and s.cited:
        return RULES["quoted_cited"]
    return RULES["paraphrase_cited"] if s.cited else RULES["paraphrase_uncited"]


def triage_matches(doc_text: str, paragraphs: Sequence[Dict[str, Any]], matches: List[Dict[str, Any]],
                   sources: Sequence[Any]) -> Dict[str, Any]:
    """Annotate each match in place with `triage` and return a summary."""
    normalized_sources = {getattr(x, "id", str(i)): _norm(getattr(x, "text", "")) for i, x in enumerate(sources)}
    counts: Dict[str, int] = {}
    for m in matches:
        s = collect_signals(doc_text, paragraphs, m, normalized_sources)
        rule = classify(m, s)
        note = None
        if m.get("match_type") == "translated" and rule.type in ("paraphrase_uncited", "paraphrase_cited"):
            note = "The source is in another language; translated reuse needs a citation exactly like a paraphrase."
        elif s.numeric_conflict:
            # The band is `review` *because* of this, so say so — an unexplained downgrade
            # is just a number the author cannot argue with (ADR-0026).
            note = ("This passage and the source share the same shape but not one figure. That often means both "
                    "follow a standard form of words rather than one copying the other — read them side by side.")
        m["triage"] = {
            "type": rule.type,
            "priority": rule.priority,
            "label": rule.label,
            "what": rule.what,
            "fix": rule.fix,
            "note": note,
            "signals": {
                "quoted": s.quoted,
                "cited": s.cited,
                "citation_markers": s.citation_markers[:6],
                "shared_by_sources": s.shared_by_sources,
                "stopword_ratio": s.stopword_ratio,
                "numeric_conflict": s.numeric_conflict,
            },
        }
        counts[rule.type] = counts.get(rule.type, 0) + 1

    ordered = sorted(counts.items(), key=lambda kv: (RULES[kv[0]].priority, -kv[1]))
    return {
        "counts": counts,
        "action_items": [
            {"type": t, "priority": RULES[t].priority, "label": RULES[t].label, "count": n}
            for t, n in ordered if RULES[t].priority <= 3
        ],
        "needs_action": sum(n for t, n in counts.items() if RULES[t].priority <= 2),
        "method": "Deterministic rules over quotation marks, nearby citation markers, the confidence band and "
                  "cross-source repetition. Pattern-based: a citation elsewhere in the paper is not seen; "
                  "self-reuse is not detected.",
    }


def rules_catalog() -> List[Dict[str, Any]]:
    return [{"type": r.type, "priority": r.priority, "label": r.label} for r in sorted(RULES.values(), key=lambda r: r.priority)]

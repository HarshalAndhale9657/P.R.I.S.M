"""
P.R.I.S.M. — Honest coaching (W9, ADR-0031)
===========================================
Turns a triaged match into a short, per-flag explanation an anxious author can act
on alone: *what this is, why the gate flagged it, the honest fix, what not to do*.
A language model **phrases** it; the deterministic triage rules (ADR-0022) decide
what it *is*, and the shown source stays the evidence.

The contract that makes this safe to ship, enforced in code rather than in a prompt:

* **Never rewrite.** The model is told not to produce replacement text, and it is
  not trusted to obey: every field it returns is passed through the **matcher as a
  post-filter** — any run of eight or more words copied from the source excerpt is
  replaced by the static rule text and the field is marked ``filtered``. Coaching can
  never hand the author copied text (ADR-0014).
* **Never coach evasion.** A lexicon check catches "lower the score", "beat the
  checker", "humanize" and friends; the same replacement applies. The CI test that
  forbids evasion wording in triage covers this module's static text too.
* **Bounded spend.** At most ``max_per_check`` calls per check (the plan says three),
  a process-wide calls-per-day cap, a timeout per call, and a cache keyed by
  (rule, passage, source, model) so the same flag never costs twice. Reported token
  usage is turned into an estimated cost and put in the result, in the open.
* **Fails soft.** No key, a timeout, bad JSON, a 5xx — the author sees the static
  rule text, never an error. ``coach_summary.skipped_reason`` says why.
* **Sends the minimum.** Only the flagged passage, the source excerpt and the rule
  label leave the server — never the whole manuscript (ZDR-friendly, LAUNCH_PLAN §11).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

from services.triage import RULES
from utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

FIELDS = ("what_it_is", "why_flagged", "honest_fix", "do_not")
_MAX_FIELD_CHARS = 600
_MAX_EXCERPT_CHARS = 700
# Triage types worth a model call. Priority 4–5 already say "usually fine"/"nothing to fix".
_COACHABLE = frozenset({"verbatim_uncited", "paraphrase_uncited", "verbatim_cited_unquoted",
                        "quoted_uncited", "paraphrase_cited", "needs_review"})

# Language whose *purpose* is hiding reuse rather than fixing it (ADR-0014). Deliberately
# the unambiguous terms only: honest guidance has to be able to say "do not just change a
# few words — that is still copying", so phrases that describe the bad practice are not
# banned; phrases that recommend beating a detector are. Copied text is caught separately,
# by the matcher.
_EVASION_RE = re.compile(
    r"\b(lower(s|ing)? (the|your) (score|similarity)|beat (the|a) (checker|detector)|"
    r"avoid(ing)? detection|evade|evading|humaniz(e|er|ers|ing)|paraphras(e|ing) tool|"
    r"spin(ning|ner)? tool|synonym(s)? (to|so) (avoid|pass|fool)|pass (the|a) (checker|detector))\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are a writing coach inside an originality checker used by authors to check their OWN manuscript before submission. You are shown ONE flagged passage from the author's draft, the source passage it matched, and the checker's deterministic classification of the flag.

Your job is to explain, not to rewrite. Respond with a single JSON object with exactly these keys, each a short plain-English string (at most 60 words):
  "what_it_is"   - what this flag means for this passage, in one or two sentences
  "why_flagged"  - the concrete features that triggered it (wording overlap, missing citation, quotation marks, figures)
  "honest_fix"   - what the author should DO: cite, quote, restate from understanding with the citation kept, or leave it
  "do_not"       - one thing the author must not do here

Hard rules:
- NEVER write a replacement or reworded version of the passage. No sample sentences. Explain the fix; do not perform it.
- NEVER suggest changing words, order, or figures to reduce similarity, and never mention scores, detectors or "passing". Reuse is fixed by attribution or by genuinely rewriting from one's own understanding, never by disguise.
- Do not accuse. The author may be the source's own author, or the overlap may be standard phrasing. Describe the text, not the person.
- Ground everything in the two passages shown; do not invent facts about the source.
- Output JSON only."""


# ── Client protocol ───────────────────────────────────────────────────────────

@dataclass
class LLMReply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int, timeout: float) -> LLMReply: ...


class OpenAIChatClient:
    """Minimal chat-completions client over ``requests`` — no SDK, nothing to audit but one URL."""

    def __init__(self, api_key: str, *, model: str = "gpt-4o-mini",
                 base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str, *, max_tokens: int, timeout: float) -> LLMReply:
        import requests

        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=timeout,
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        return LLMReply(text=data["choices"][0]["message"]["content"],
                        prompt_tokens=int(usage.get("prompt_tokens", 0)),
                        completion_tokens=int(usage.get("completion_tokens", 0)))


# gpt-4o-mini list price, USD per 1M tokens, so the number in the result is an estimate an
# operator can sanity-check against the bill — not a claim of the exact charge.
_PRICE_PER_M = {"gpt-4o-mini": (0.15, 0.60)}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = _PRICE_PER_M.get(model, (0.0, 0.0))
    return round((prompt_tokens * pin + completion_tokens * pout) / 1_000_000, 6)


# ── Budget ────────────────────────────────────────────────────────────────────

class CoachBudget:
    """Process-wide daily call cap. Cheap insurance, not the per-account ceiling (that is W11)."""

    def __init__(self, max_calls_per_day: int = 500) -> None:
        self.max_calls_per_day = max_calls_per_day
        self._day = 0
        self._calls = 0
        self._lock = threading.Lock()

    def take(self, now: Optional[float] = None) -> bool:
        day = int((time.time() if now is None else now) // 86400)
        with self._lock:
            if day != self._day:
                self._day, self._calls = day, 0
            if self.max_calls_per_day and self._calls >= self.max_calls_per_day:
                return False
            self._calls += 1
            return True

    @property
    def calls_today(self) -> int:
        return self._calls


# ── Post-filter ───────────────────────────────────────────────────────────────

def _verbatim_run(text: str, source: str, min_words: int) -> bool:
    """True if `text` contains a run of `min_words` consecutive words also in `source`."""
    from services.plagiarism_matcher import tokenize

    a = [t.norm for t in tokenize(text)]
    b = [t.norm for t in tokenize(source)]
    if len(a) < min_words or len(b) < min_words:
        return False
    grams = {tuple(b[i:i + min_words]) for i in range(len(b) - min_words + 1)}
    return any(tuple(a[i:i + min_words]) in grams for i in range(len(a) - min_words + 1))


def post_filter(card: Dict[str, str], *, source_excerpt: str, doc_excerpt: str,
                fallback: Dict[str, str], min_words: int = 8) -> List[str]:
    """Replace any field that launders the source, reproduces the passage, or coaches evasion.

    Returns the names of the fields replaced. Mutates `card` in place.
    """
    replaced: List[str] = []
    for key in FIELDS:
        val = (card.get(key) or "").strip()
        bad = (
            not val
            or len(val) > _MAX_FIELD_CHARS
            or _EVASION_RE.search(val)
            or _verbatim_run(val, source_excerpt, min_words)
            or _verbatim_run(val, doc_excerpt, min_words)
        )
        if bad:
            card[key] = fallback[key]
            replaced.append(key)
    return replaced


def static_card(rule_type: str) -> Dict[str, str]:
    """The deterministic text for a triage type — what the author sees when the model does not run."""
    rule = RULES.get(rule_type) or RULES["needs_review"]
    return {
        "what_it_is": rule.what,
        "why_flagged": "Classified by rule from quotation marks, nearby citation markers, the confidence band and "
                       "cross-source repetition.",
        "honest_fix": rule.fix,
        "do_not": "Do not just change a few words and leave it — that is still copying, and it hides the problem "
                  "from you rather than fixing it.",
    }


# ── Coaching ──────────────────────────────────────────────────────────────────

@dataclass
class CoachStats:
    coached: int = 0
    calls: int = 0
    cached: int = 0
    filtered_fields: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    skipped_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)


def _cache_key(model: str, rule_type: str, doc_excerpt: str, source_excerpt: str) -> str:
    h = hashlib.sha1()
    for part in (model, rule_type, doc_excerpt, source_excerpt):
        h.update(part.encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()


def _user_prompt(rule_type: str, label: str, doc_excerpt: str, source_excerpt: str, signals: Dict[str, Any]) -> str:
    return (
        f"Classification: {rule_type} ({label}).\n"
        f"Signals: quoted={signals.get('quoted')}, cited_nearby={signals.get('cited')}, "
        f"confidence_band={signals.get('band')}, shared_by_sources={signals.get('shared_by_sources', 1)}, "
        f"numeric_conflict={signals.get('numeric_conflict', False)}.\n\n"
        f"AUTHOR'S PASSAGE:\n{doc_excerpt[:_MAX_EXCERPT_CHARS]}\n\n"
        f"MATCHED SOURCE PASSAGE:\n{source_excerpt[:_MAX_EXCERPT_CHARS]}\n"
    )


def _select(matches: Sequence[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """The flags most worth a call: lowest priority number first, then highest similarity."""
    cands = [m for m in matches if (m.get("triage") or {}).get("type") in _COACHABLE]
    cands.sort(key=lambda m: ((m.get("triage") or {}).get("priority", 9), -float(m.get("similarity", 0.0))))
    return cands[:limit]


def coach_matches(
    matches: List[Dict[str, Any]],
    *,
    client: Optional[LLMClient],
    cache: TTLCache,
    budget: CoachBudget,
    max_per_check: int = 3,
    timeout: float = 20.0,
    max_tokens: int = 400,
) -> Dict[str, Any]:
    """Annotate up to `max_per_check` matches in place with `coach`; return the summary."""
    stats = CoachStats()
    method = ("A language model phrases the explanation for the highest-priority flags; the classification "
              "itself is rule-based. Every sentence it writes is checked against the source and the passage — "
              "anything that copies either, or suggests disguising reuse, is replaced by the rule's own text.")
    if client is None:
        stats.skipped_reason = "not configured"
        return _summary(stats, None, method)

    for m in _select(matches, max_per_check):
        t = m.get("triage") or {}
        rule_type = t.get("type", "needs_review")
        doc_excerpt = (m.get("doc_excerpt") or "")[:_MAX_EXCERPT_CHARS]
        src_excerpt = (m.get("source_excerpt") or "")[:_MAX_EXCERPT_CHARS]
        fallback = static_card(rule_type)
        key = _cache_key(client.model, rule_type, doc_excerpt, src_excerpt)

        card = cache.get(key)
        cached = card is not None
        if not cached:
            if not budget.take():
                stats.skipped_reason = "daily call cap reached"
                break
            signals = dict(t.get("signals") or {})
            signals["band"] = m.get("confidence")
            try:
                reply = client.complete(SYSTEM_PROMPT, _user_prompt(rule_type, t.get("label", ""), doc_excerpt,
                                                                    src_excerpt, signals),
                                        max_tokens=max_tokens, timeout=timeout)
                stats.calls += 1
                stats.prompt_tokens += reply.prompt_tokens
                stats.completion_tokens += reply.completion_tokens
                parsed = json.loads(reply.text)
                if not isinstance(parsed, dict):
                    raise ValueError("model did not return a JSON object")
                card = {k: str(parsed.get(k, "") or "") for k in FIELDS}
            except Exception as exc:                      # timeouts, 5xx, bad JSON — all soft
                logger.warning("coach call failed (%s); using rule text", type(exc).__name__)
                stats.errors.append(type(exc).__name__)
                continue
            replaced = post_filter(card, source_excerpt=src_excerpt, doc_excerpt=doc_excerpt, fallback=fallback)
            card["filtered"] = replaced
            stats.filtered_fields += len(replaced)
            cache.put(key, dict(card))
        else:
            stats.cached += 1

        m["coach"] = {**{k: card[k] for k in FIELDS}, "filtered": list(card.get("filtered", [])),
                      "model": client.model, "cached": cached,
                      "ai_written": True, "source_visible": True}
        stats.coached += 1

    return _summary(stats, client.model, method)


def _summary(stats: CoachStats, model: Optional[str], method: str) -> Dict[str, Any]:
    return {
        "coached": stats.coached,
        "calls": stats.calls,
        "cached": stats.cached,
        "filtered_fields": stats.filtered_fields,
        "model": model,
        "prompt_tokens": stats.prompt_tokens,
        "completion_tokens": stats.completion_tokens,
        "estimated_cost_usd": estimate_cost_usd(model or "", stats.prompt_tokens, stats.completion_tokens),
        "skipped_reason": stats.skipped_reason,
        "errors": stats.errors,
        "method": method,
    }


__all__ = ["LLMClient", "LLMReply", "OpenAIChatClient", "CoachBudget", "coach_matches", "post_filter",
           "static_card", "estimate_cost_usd", "SYSTEM_PROMPT", "FIELDS"]

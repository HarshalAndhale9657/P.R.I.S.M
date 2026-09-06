"""Honest coaching (W9, ADR-0031) — a fake model, so every guarantee is tested offline."""
import json

import pytest

from services.coach import (
    FIELDS,
    CoachBudget,
    LLMReply,
    coach_matches,
    estimate_cost_usd,
    post_filter,
    static_card,
)
from utils.ttl_cache import TTLCache

SOURCE = ("Attention mechanisms permit the model to weigh the relevance of each token with respect to "
          "every other token, thereby capturing long-range dependencies that recurrent networks struggle to represent.")
PASSAGE = ("By letting the model score how relevant each token is to every other token, attention captures "
           "dependencies over long distances that recurrent models find hard.")

GOOD = {
    "what_it_is": "This passage closely restates a source sentence without a citation nearby.",
    "why_flagged": "The sentence structure and technical phrasing track the source closely, and no citation marker was found.",
    "honest_fix": "Add a citation to the source. If you drew on it, keep the citation and restate the idea from your own understanding.",
    "do_not": "Do not leave it uncited.",
}


class FakeModel:
    model = "fake-model"

    def __init__(self, reply=None, *, raise_exc=None):
        self.reply = reply if reply is not None else GOOD
        self.raise_exc = raise_exc
        self.calls = []

    def complete(self, system, user, *, max_tokens, timeout):
        self.calls.append(user)
        if self.raise_exc:
            raise self.raise_exc
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return LLMReply(text=text, prompt_tokens=300, completion_tokens=120)


def _match(prio=1, rule="paraphrase_uncited", sim=0.88, doc=PASSAGE, src=SOURCE):
    return {"match_type": "paraphrase", "similarity": sim, "confidence": "confident",
            "doc_excerpt": doc, "source_excerpt": src,
            "triage": {"type": rule, "priority": prio, "label": "Close paraphrase, no citation",
                       "signals": {"quoted": False, "cited": False}}}


def _run(matches, client, **kw):
    kw.setdefault("cache", TTLCache(max_size=32, ttl_seconds=60))
    kw.setdefault("budget", CoachBudget(100))
    return coach_matches(matches, client=client, **kw)


# ── Happy path, selection, budget, cache ──────────────────────────────────────

def test_a_good_reply_becomes_a_labelled_ai_written_card():
    m = _match()
    s = _run([m], FakeModel())
    assert s["coached"] == 1 and s["calls"] == 1 and s["skipped_reason"] is None
    card = m["coach"]
    assert {k: card[k] for k in FIELDS} == GOOD
    assert card["ai_written"] is True and card["source_visible"] is True and card["filtered"] == []
    assert s["estimated_cost_usd"] == 0.0, "an unknown model has no price on file; never guess a cost"


def test_at_most_max_per_check_calls_highest_priority_first():
    # Distinct passages, so each is a distinct flag (identical flags would rightly hit the cache).
    ms = [_match(prio=3, rule="paraphrase_cited", sim=0.9, doc="p3 " + PASSAGE), _match(prio=1, sim=0.7, doc="p1 low " + PASSAGE),
          _match(prio=1, sim=0.95, doc="p1 high " + PASSAGE), _match(prio=2, rule="quoted_uncited", doc="p2 " + PASSAGE),
          _match(prio=4, rule="common_phrase", doc="p4 " + PASSAGE)]
    fake = FakeModel()
    s = _run(ms, fake, max_per_check=3)
    assert s["calls"] == 3 and s["coached"] == 3
    coached = [m for m in ms if "coach" in m]
    assert sorted(m["triage"]["priority"] for m in coached) == [1, 1, 2]
    assert "coach" not in ms[0], "the priority-3 flag lost to the three ahead of it"
    assert "coach" not in ms[4], "priority-4 flags are never worth a call"
    # Ties on priority go to the higher similarity: with a budget of one, the 0.95 flag wins.
    ms2 = [_match(prio=1, sim=0.7, doc="low " + PASSAGE), _match(prio=1, sim=0.95, doc="high " + PASSAGE)]
    _run(ms2, FakeModel(), max_per_check=1)
    assert "coach" in ms2[1] and "coach" not in ms2[0]


def test_identical_flags_are_served_from_cache():
    cache = TTLCache(max_size=8, ttl_seconds=60)
    fake = FakeModel()
    _run([_match()], fake, cache=cache)
    s = _run([_match()], fake, cache=cache)
    assert len(fake.calls) == 1 and s["cached"] == 1 and s["calls"] == 0


def test_daily_call_cap_stops_calls_and_says_so():
    fake = FakeModel()
    budget = CoachBudget(max_calls_per_day=1)
    s = _run([_match(), _match(doc=PASSAGE + " More."), _match(doc=PASSAGE + " Again.")], fake, budget=budget)
    assert s["calls"] == 1 and s["skipped_reason"] == "daily call cap reached"


def test_not_configured_means_no_cards_and_a_stated_reason():
    m = _match()
    s = _run([m], None)
    assert "coach" not in m and s["skipped_reason"] == "not configured" and s["calls"] == 0


# ── Failing soft ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["not json at all", json.dumps(["a", "list"]), json.dumps({"what_it_is": "x"})])
def test_bad_replies_never_raise_and_fall_back_to_rule_text(bad):
    m = _match()
    s = _run([m], FakeModel(reply=bad))
    if bad.startswith("{"):
        # A partial object is accepted, and the missing fields are the rule text (filtered).
        assert m["coach"]["honest_fix"] == static_card("paraphrase_uncited")["honest_fix"]
        assert "honest_fix" in m["coach"]["filtered"]
    else:
        assert "coach" not in m and s["errors"], "malformed output is an error, not a card"


def test_a_raising_client_never_sinks_the_check():
    m = _match()
    s = _run([m], FakeModel(raise_exc=TimeoutError("slow")))
    assert "coach" not in m and s["errors"] == ["TimeoutError"]


# ── The guarantees ADR-0014 needs ─────────────────────────────────────────────

def test_post_filter_replaces_a_field_that_copies_the_source():
    """The matcher as a post-filter: coaching can never hand the author copied text."""
    card = dict(GOOD)
    card["honest_fix"] = "Try writing it like this: " + SOURCE
    replaced = post_filter(card, source_excerpt=SOURCE, doc_excerpt=PASSAGE, fallback=static_card("paraphrase_uncited"))
    assert replaced == ["honest_fix"]
    assert card["honest_fix"] == static_card("paraphrase_uncited")["honest_fix"]


def test_post_filter_replaces_a_field_that_reproduces_the_passage():
    card = dict(GOOD)
    card["what_it_is"] = "Your sentence reads: " + PASSAGE
    assert post_filter(card, source_excerpt=SOURCE, doc_excerpt=PASSAGE, fallback=static_card("paraphrase_uncited")) == ["what_it_is"]


@pytest.mark.parametrize("phrase", [
    "Change a few words so it reads differently and lowers the score.",
    "Run it through a paraphrasing tool to beat the checker.",
    "Humanize the text to avoid detection.",
])
def test_post_filter_replaces_evasion_coaching(phrase):
    card = dict(GOOD)
    card["do_not"] = phrase
    assert post_filter(card, source_excerpt=SOURCE, doc_excerpt=PASSAGE, fallback=static_card("paraphrase_uncited")) == ["do_not"]


def test_filtered_fields_are_visible_on_the_card_and_counted():
    bad = dict(GOOD)
    bad["honest_fix"] = SOURCE
    m = _match()
    s = _run([m], FakeModel(reply=bad))
    assert m["coach"]["filtered"] == ["honest_fix"] and s["filtered_fields"] == 1


def test_static_cards_never_suggest_evasion():
    from services.coach import _EVASION_RE
    for rule in ("verbatim_uncited", "paraphrase_uncited", "verbatim_cited_unquoted", "quoted_uncited",
                 "paraphrase_cited", "needs_review", "common_phrase", "quoted_cited"):
        for k, v in static_card(rule).items():
            assert not _EVASION_RE.search(v), (rule, k, v)


def test_the_prompt_sends_only_the_two_passages_not_the_manuscript():
    fake = FakeModel()
    m = _match()
    _run([m], fake)
    sent = fake.calls[0]
    assert PASSAGE in sent and SOURCE in sent
    assert "document_text" not in sent and len(sent) < 2500


def test_cost_estimate_uses_list_price_only_for_known_models():
    assert estimate_cost_usd("gpt-4o-mini", 1_000_000, 0) == 0.15
    assert estimate_cost_usd("gpt-4o-mini", 0, 1_000_000) == 0.6
    assert estimate_cost_usd("something-else", 1_000_000, 1_000_000) == 0.0


# ── Through the pipeline ──────────────────────────────────────────────────────

def test_the_stage_annotates_matches_and_the_result_carries_the_summary():
    from pipeline.base import CheckContext
    from pipeline.stages import CoachStage
    ctx = CheckContext()
    ctx.artifacts["matches"] = [_match()]
    stage = CoachStage(client=FakeModel(), cache=TTLCache(max_size=8, ttl_seconds=60), budget=CoachBudget(10),
                       max_per_check=3, timeout=5.0)
    stage.run(ctx)
    assert ctx.artifacts["matches"][0]["coach"]["what_it_is"] == GOOD["what_it_is"]
    assert ctx.artifacts["coach_summary"]["coached"] == 1


def test_the_stage_is_inert_without_a_client():
    from pipeline.base import CheckContext
    from pipeline.stages import CoachStage
    ctx = CheckContext()
    ctx.artifacts["matches"] = [_match()]
    CoachStage(client=None, cache=TTLCache(), budget=CoachBudget(10)).run(ctx)
    assert "coach" not in ctx.artifacts["matches"][0]
    assert ctx.artifacts["coach_summary"]["skipped_reason"] == "not configured"

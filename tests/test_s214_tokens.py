"""S214 acceptance: golden labeled-manifest tests.

Counts are reproducible and quality labels correct: exact tokenizer ->
EXACT manifests with exact totals; no tokenizer -> ESTIMATED; provider
usage -> PROVIDER; combined labels degrade to the weakest part.
"""

from runmal.prompt import baseline_order, compose, make_slot
from runmal.prompt.slots import Slot
from runmal.tokens import (
    TokenQuality,
    count_from_provider_usage,
    count_tokens,
    worst_quality,
)


def word_tokenizer(text: str) -> int:
    """Deterministic exact test tokenizer: one token per word."""
    return max(1, len(text.split()))


def golden_slots():
    return [
        make_slot("main_system", "system", "one two three four",
                  id="sys", required=True),                    # 4 words / 4 est
        make_slot("persona", "system", "five six",
                  id="persona"),                               # 2 words / 1 est
        Slot(id="history", kind="history", role="user",
             order=baseline_order("history"), splittable=True,
             parts=("seven eight nine", "ten")),                # 5 words / 4 est
    ]


def test_golden_manifest_exact_label_and_totals():
    result = compose(golden_slots(), context_limit=1000, reserve_response=100,
                     counter=word_tokenizer)
    m = result.manifest
    assert m.count_quality == TokenQuality.EXACT
    # 4 + 2 + (3+1 joined words = 4)... history parts join with "\n", which
    # the word tokenizer still splits into the same 4 words.
    assert {u.slot_id: u.tokens for u in m.included} == {
        "sys": 4, "persona": 2, "history": 4,
    }
    assert m.total_input_tokens == 10


def test_golden_manifest_estimated_label_and_totals():
    result = compose(golden_slots(), context_limit=1000, reserve_response=100)
    m = result.manifest
    assert m.count_quality == TokenQuality.ESTIMATED
    # estimate: len//4, min 1. sys 18 chars -> 4; persona 8 chars -> 2;
    # history joined "seven eight nine\nten" = 21 chars -> 5.
    assert {u.slot_id: u.tokens for u in m.included} == {
        "sys": 4, "persona": 2, "history": 5,
    }
    assert m.total_input_tokens == 11


def test_manifests_reproducible():
    a = compose(golden_slots(), context_limit=1000, reserve_response=100,
                counter=word_tokenizer)
    b = compose(golden_slots(), context_limit=1000, reserve_response=100,
                counter=word_tokenizer)
    assert a == b  # identical input, identical manifest, every time


def test_count_tokens_labels():
    exact = count_tokens("hello wide world", tokenizer=word_tokenizer)
    assert (exact.value, exact.quality) == (3, TokenQuality.EXACT)
    # the plain estimate path is labeled as such when no tokenizer exists
    import runmal.tokens as tokens_mod

    original = tokens_mod.get_exact_tokenizer
    tokens_mod.get_exact_tokenizer = lambda: None
    try:
        est = count_tokens("hello wide world")
    finally:
        tokens_mod.get_exact_tokenizer = original
    assert est.quality == TokenQuality.ESTIMATED
    assert est.value == max(1, len("hello wide world") // 4)


def test_provider_usage_counts():
    c = count_from_provider_usage({"prompt_tokens": 123, "completion_tokens": 9})
    assert (c.value, c.quality) == (123, TokenQuality.PROVIDER)
    c2 = count_from_provider_usage({"input_tokens": 7})
    assert (c2.value, c2.quality) == (7, TokenQuality.PROVIDER)
    assert count_from_provider_usage({}) is None
    assert count_from_provider_usage(None) is None
    assert count_from_provider_usage({"prompt_tokens": "many"}) is None
    assert count_from_provider_usage({"prompt_tokens": True}) is None


def test_worst_quality_degrades():
    assert worst_quality([TokenQuality.EXACT]) == TokenQuality.EXACT
    assert worst_quality(
        [TokenQuality.EXACT, TokenQuality.PROVIDER]
    ) == TokenQuality.PROVIDER
    assert worst_quality(
        [TokenQuality.EXACT, TokenQuality.ESTIMATED, TokenQuality.PROVIDER]
    ) == TokenQuality.ESTIMATED
    assert worst_quality([]) == TokenQuality.ESTIMATED


def test_exact_counter_changes_budget_outcome():
    # Budget 10: exact counts (4+2+4) fit whole; estimates (4+2+5) force
    # the history slot to trim its oldest part.
    exact = compose(golden_slots(), context_limit=10, reserve_response=0,
                    counter=word_tokenizer)
    exact_hist = next(u for u in exact.manifest.included if u.slot_id == "history")
    assert exact_hist.trimmed_parts == 0
    est = compose(golden_slots(), context_limit=10, reserve_response=0)
    est_hist = next(u for u in est.manifest.included if u.slot_id == "history")
    assert est_hist.trimmed_parts == 1
    assert est.manifest.total_input_tokens <= 10

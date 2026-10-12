"""Roadmap S214 acceptance: Prompt Trace + token ledger.

- The trace carries included/discarded slots with discard reasons, token
  counts + count quality, lore triggers, memory placeholders and
  whitelisted backend metadata.
- A golden fixture pins the serialized trace shape.
- Secrets are provably absent: canary strings planted in slot content
  and in backend metadata never appear in the serialized trace.
"""

import json
import os
from pathlib import Path

from runmal.prompt.composer import compose
from runmal.prompt.slots import make_slot
from runmal.prompt.trace import build_trace, trace_to_dict

GOLDEN = Path(__file__).parent / "fixtures" / "prompt" / "trace_basic.json"
CANARY = "CANARY-SECRET-9f3b7d"


def fixture_slots():
    return [
        make_slot("main_system", "system", "You are Rúnmál.", required=True, id="sys"),
        make_slot("persona", "system", "Bryn the smith.", id="persona"),
        make_slot(
            "lore_before",
            "system",
            "The harbor freezes in winter.",
            id="lore/harbor",
            trigger="harbor",
            provenance="lorebook:World",
        ),
        make_slot(
            "memory_retrieved",
            "system",
            "(memory placeholder)",
            id="mem/1",
            provenance="memory",
        ),
        make_slot(
            "history",
            "user",
            "",
            id="history",
            splittable=True,
            parts=("First exchange.", "Second exchange."),
        ),
        make_slot("post_history", "system", "x" * 4000, id="too-big"),
    ]


def fixture_trace():
    slots = fixture_slots()
    composed = compose(slots, context_limit=512, reserve_response=64, overhead=8)
    return build_trace(
        composed,
        slots,
        backend={
            "backend": "openrouter",
            "model": "test/model",
            "api_key": CANARY,  # must be dropped by the whitelist
            "headers": {"Authorization": f"Bearer {CANARY}"},
        },
    )


def test_trace_golden_fixture() -> None:
    data = trace_to_dict(fixture_trace())
    if os.environ.get("RUNMAL_UPDATE_GOLDENS"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    assert data == expected


def test_trace_answers_why() -> None:
    trace = fixture_trace()
    by_id = {s.slot_id: s for s in trace.slots}
    assert by_id["lore/harbor"].status == "included"
    assert by_id["lore/harbor"].trigger == "harbor"
    assert by_id["too-big"].status == "discarded"
    assert by_id["too-big"].reason == "over_input_budget"
    assert [t.slot_id for t in trace.lore_triggers] == ["lore/harbor"]
    assert [m.slot_id for m in trace.memory_slots] == ["mem/1"]


def test_ledger_accounts_for_every_token() -> None:
    ledger = fixture_trace().ledger
    assert ledger.input_budget == 512 - 64 - 8
    assert ledger.total_input_tokens + ledger.remaining_input_tokens == (ledger.input_budget)
    assert ledger.count_quality.value == "estimated"


def test_secrets_provably_absent() -> None:
    slots = fixture_slots()
    slots[1] = make_slot("persona", "system", f"Persona text hiding {CANARY}", id="persona")
    composed = compose(slots, context_limit=512, reserve_response=64, overhead=8)
    trace = build_trace(composed, slots, backend={"backend": "ollama", "api_key": CANARY})
    blob = json.dumps(trace_to_dict(trace))
    assert CANARY not in blob
    assert "api_key" not in blob
    assert "Persona text hiding" not in blob  # content never enters a trace
    assert trace.backend == {"backend": "ollama"}

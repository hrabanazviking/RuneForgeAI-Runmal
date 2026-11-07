"""P-044 acceptance: lore token accounting.

Pure tests (fake rows / fake trace dicts, no DB), preview tests
(ORM-fake entries reusing the test_p041 orm_entry pattern), and
one inspector reconciliation test (test_s215 harness pattern).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.lorebooks.accounting import account_from_rows, account_from_trace, count_lore_tokens
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scopes import _apply_layer_budget
from runmal.prompt.composer import compose
from runmal.prompt.inspect import MAIN_SYSTEM_TEXT, _lore_slot
from runmal.prompt.slots import make_slot
from runmal.prompt.trace import build_trace, trace_to_dict
from runmal.tokens import estimate_tokens


def orm_entry(eid, name, content, keys=(), **kw):
    # Reused pattern from tests/test_p041_vectorised_lore.py;
    # vectorised defaults False here so keyword entries can fire.
    base = dict(
        id=eid, name=name, content=content, enabled=True, constant=False,
        vectorised=False, keys_json=json.dumps(list(keys)),
        secondary_keys_json="[]", whole_word=True, case_sensitive=False,
        selective_logic="and_any", sticky_prompts=0, cooldown_prompts=0,
        delay_prompts=0, inclusion_group="", group_weight=100, priority=100,
        probability=100, position="before_char", depth=None, role="system",
    )
    base.update(kw)
    return SimpleNamespace(**base)

# ---------------------------------------------------------- count

def test_count_lore_tokens_matches_estimate():
    for text in ("", "a", "abcd", "hello world this is lore",
                 "Dragons soar above the peaks and guard gold"):
        assert count_lore_tokens(text) == estimate_tokens(text)
    assert count_lore_tokens("") == 1

def test_count_lore_tokens_custom_counter_exact():
    counter = lambda t: len(t.split())  # noqa: E731
    assert count_lore_tokens("a b c d e", counter) == 5
    assert count_lore_tokens("a b c d e", counter) != estimate_tokens("a b c d e")
    assert count_lore_tokens("one two", counter) == 2

def test_count_lore_tokens_rejects_non_str():
    for bad in (None, 123, b"bytes", ["x"], 1.5):
        with pytest.raises(ValueError):
            count_lore_tokens(bad)

# ------------------------------------------------- account_from_rows

def _mixed_rows():
    return [
        {"entry_id": "a", "status": "included", "tokens": 10,
         "lorebook_id": "book1", "scope": "global"},
        {"entry_id": "b", "status": "included", "tokens": 5,
         "lorebook_id": "book1", "scope": "global"},
        {"entry_id": "c", "status": "discarded", "tokens": 7,
         "lorebook_id": "book2", "scope": "chat"},
        {"entry_id": "d", "status": "not_triggered", "tokens": None,
         "lorebook_id": "book2", "scope": "chat"},
    ]

def test_account_mixed_statuses_arithmetic():
    acc = account_from_rows(_mixed_rows(), token_budget=20).to_dict()
    assert acc["tokens_used"] == 15
    assert acc["discarded_tokens"] == 7
    assert acc["budget_remaining"] == 5
    assert acc["token_budget"] == 20
    assert acc["count_quality"] == "estimated"
    assert acc["by_status"]["included"] == {"count": 2, "tokens": 15, "spent": 15}
    assert acc["by_status"]["discarded"] == {"count": 1, "tokens": 7, "spent": 0}
    assert acc["by_status"]["not_triggered"] == {"count": 1, "tokens": 0, "spent": 0}
    assert acc["by_book"]["book1"] == {"tokens_used": 15, "entries": 2}
    assert acc["by_book"]["book2"] == {"tokens_used": 0, "entries": 2}
    spent = {e["entry_id"]: e["spent"] for e in acc["entries"]}
    assert spent == {"a": 10, "b": 5, "c": 0, "d": 0}

def test_account_unlimited_budget():
    acc = account_from_rows(_mixed_rows(), token_budget=None).to_dict()
    assert acc["token_budget"] is None
    assert acc["budget_remaining"] is None
    assert acc["tokens_used"] == 15

def test_account_zero_budget_unclamped():
    rows = [{"entry_id": "a", "status": "included", "tokens": 10}]
    acc = account_from_rows(rows, token_budget=0).to_dict()
    assert acc["token_budget"] == 0
    assert acc["budget_remaining"] == -10  # == -tokens_used, unclamped
    muted = [{"entry_id": "c", "status": "discarded", "tokens": 7}]
    acc0 = account_from_rows(muted, token_budget=0).to_dict()
    assert acc0["tokens_used"] == 0
    assert acc0["budget_remaining"] == 0

def test_account_negative_budget_raises():
    for bad in (-1, -100):
        with pytest.raises(ValueError):
            account_from_rows(_mixed_rows(), token_budget=bad)

def test_account_included_without_count_raises_and_contents_fill():
    row = {"entry_id": "a", "status": "included", "tokens": None}
    with pytest.raises(ValueError):
        account_from_rows([dict(row)], token_budget=None)
    content = "hello world lore content here"
    acc = account_from_rows([dict(row)], token_budget=None,
                            contents={"a": content}).to_dict()
    assert acc["tokens_used"] == estimate_tokens(content)
    assert acc["entries"][0]["tokens"] == estimate_tokens(content)

def _untriggered_rows():
    return [
        {"entry_id": "inc", "status": "included", "tokens": 4},
        {"entry_id": "nt", "status": "not_triggered", "tokens": None},
        {"entry_id": "dis", "status": "disabled", "tokens": None},
        {"entry_id": "ge", "status": "group_excluded", "tokens": None},
        {"entry_id": "miss", "status": "not_triggered", "tokens": None},
    ]

def test_account_untriggered_tokens_honesty():
    acc_no = account_from_rows(_untriggered_rows(), token_budget=None).to_dict()
    assert acc_no["untriggered_tokens"] is None
    contents = {"nt": "aaaa bbbb cccc dddd", "dis": "eeee ffff gggg",
                "ge": "hhhh iiii"}
    acc = account_from_rows(_untriggered_rows(), token_budget=None,
                            contents=contents).to_dict()
    expected = sum(estimate_tokens(c) for c in contents.values())
    assert acc["untriggered_tokens"] == expected
    by_id = {e["entry_id"]: e for e in acc["entries"]}
    assert by_id["nt"]["tokens"] == estimate_tokens(contents["nt"])
    assert by_id["miss"]["tokens"] is None  # missing from contents: 0
    assert by_id["miss"]["spent"] == 0

def test_account_counter_exact_and_fills_use_counter():
    counter = lambda t: len(t.split())  # noqa: E731
    rows = [{"entry_id": "a", "status": "included", "tokens": None},
            {"entry_id": "b", "status": "not_triggered", "tokens": None}]
    contents = {"a": "a b c d e f", "b": "x y z"}
    acc = account_from_rows(rows, token_budget=None, counter=counter,
                            contents=contents).to_dict()
    assert acc["count_quality"] == "exact"
    assert acc["tokens_used"] == 6
    assert acc["untriggered_tokens"] == 3
    assert acc["tokens_used"] != estimate_tokens(contents["a"])

def test_account_json_serialisable_and_content_free():
    secret = "SECRET-CONTENT-XYZ-12345"
    content = secret + " lore filling the included row"
    rows = [{"entry_id": "a", "status": "included", "tokens": None}]
    acc = account_from_rows(rows, token_budget=50,
                            contents={"a": content}).to_dict()
    dumped = json.dumps(acc)  # must not raise
    assert secret not in dumped
    assert content not in dumped
    assert set(acc) == {"tokens_used", "token_budget", "budget_remaining",
                        "count_quality", "entries", "by_status", "by_book",
                        "discarded_tokens", "untriggered_tokens"}

# ------------------------------------------------ account_from_trace

def _trace(slots, total=100, budget=200, remaining=100):
    return {"ledger": {"total_input_tokens": total, "input_budget": budget,
                       "remaining_input_tokens": remaining,
                       "count_quality": "estimated"}, "slots": slots}

def _slot(sid, kind, status, tokens, prov="", trigger=None):
    return {"slot_id": sid, "kind": kind, "status": status,
            "tokens": tokens, "provenance": prov, "trigger": trigger}

def test_account_from_trace_lore_only_and_shares():
    trace = _trace([
        _slot("lore/1", "lore_before", "included", 10, "lorebook:A", "dragon"),
        _slot("lore/2", "lore_after", "included", 5, "lorebook:A", "constant"),
        _slot("lore/3", "lore_before", "discarded", 7, "lorebook:B", "harbor"),
        _slot("sys", "main_system", "included", 20),
        _slot("hist", "history", "discarded", 30),
    ])
    acc = account_from_trace(trace)
    assert acc["tokens_used"] == 15
    assert acc["discarded_tokens"] == 7
    assert acc["total_input_tokens"] == 100
    assert acc["input_budget"] == 200
    assert acc["remaining_input_tokens"] == 100
    assert acc["share_of_input"] == pytest.approx(0.15)
    assert acc["share_of_budget"] == pytest.approx(0.075)
    assert acc["count_quality"] == "estimated"
    assert len(acc["entries"]) == 3
    prov = acc["by_provenance"]
    assert prov["lorebook:A"] == {"tokens_used": 15, "discarded_tokens": 0, "entries": 2}
    assert prov["lorebook:B"] == {"tokens_used": 0, "discarded_tokens": 7, "entries": 1}
    assert sum(v["tokens_used"] for v in prov.values()) == acc["tokens_used"]
    assert sum(v["discarded_tokens"] for v in prov.values()) == acc["discarded_tokens"]

def test_account_from_trace_empty_slots():
    acc = account_from_trace(_trace([], total=0, budget=0, remaining=0))
    assert acc["tokens_used"] == 0
    assert acc["discarded_tokens"] == 0
    assert acc["share_of_input"] == 0.0
    assert acc["share_of_budget"] == 0.0
    assert acc["entries"] == []
    assert acc["by_provenance"] == {}

# ------------------------------------------------------------- preview

INC_CONTENT = "Dragons soar above the mountain peaks and guard gold"
DISC_CONTENT = "Dragons hoard ancient gold beneath the dark mountain halls"
UNTRIG_CONTENT = "Quiet lore about silent forests and hidden streams"

def _preview_entries():
    return [
        orm_entry("inc", "Included", INC_CONTENT, ("dragon",), priority=200),
        orm_entry("disc", "Discarded", DISC_CONTENT, ("dragon",), priority=100),
        orm_entry("untrig", "Untriggered", UNTRIG_CONTENT, ("zzz-absent",)),
    ]

def _preview(counter=None):
    return preview_activation(_preview_entries(), ["a dragon rises"], 4,
                              estimate_tokens(INC_CONTENT), counter=counter)

def _rows_by_id(preview):
    return {r["entry_id"]: r for r in preview["entries"]}

def _acct_by_id(preview):
    return {e["entry_id"]: e for e in preview["token_account"]["entries"]}

def test_preview_token_account_reconciles():
    preview = _preview()
    rows = _rows_by_id(preview)
    assert rows["inc"]["status"] == "included"
    assert rows["disc"]["status"] == "discarded"
    account = preview["token_account"]
    assert account["tokens_used"] == preview["tokens_used"]
    assert account["tokens_used"] == sum(
        r["tokens"] for r in rows.values() if r["status"] == "included")
    acct = _acct_by_id(preview)
    for eid in ("inc", "disc"):
        assert acct[eid]["tokens"] == rows[eid]["tokens"]
        assert acct[eid]["status"] == rows[eid]["status"]
    assert acct["inc"]["spent"] == rows["inc"]["tokens"]
    assert acct["disc"]["spent"] == 0
    assert account["discarded_tokens"] == rows["disc"]["tokens"]
    assert account["token_budget"] == preview["token_budget"]

def test_preview_untriggered_would_be_from_stored_content():
    preview = _preview()
    rows = _rows_by_id(preview)
    assert rows["untrig"]["status"] == "not_triggered"
    assert rows["untrig"]["tokens"] is None  # budget pass never counted it
    acct = _acct_by_id(preview)
    assert acct["untrig"]["tokens"] == estimate_tokens(UNTRIG_CONTENT)
    assert acct["untrig"]["spent"] == 0
    assert preview["token_account"]["untriggered_tokens"] == estimate_tokens(UNTRIG_CONTENT)

def test_preview_with_counter_exact_but_row_tokens_unchanged():
    counter = lambda t: len(t.split())  # noqa: E731
    assert counter(INC_CONTENT) != estimate_tokens(INC_CONTENT)
    preview = _preview(counter=counter)
    rows = _rows_by_id(preview)
    assert rows["inc"]["status"] == "included"
    # Budget-pass number on the row is still the canonical estimate.
    assert rows["inc"]["tokens"] == estimate_tokens(INC_CONTENT)
    account = preview["token_account"]
    assert account["count_quality"] == "exact"
    acct = _acct_by_id(preview)
    assert acct["inc"]["tokens"] == counter(INC_CONTENT)
    assert account["tokens_used"] == counter(INC_CONTENT)

def test_preview_existing_keys_unchanged():
    preview = preview_activation(_preview_entries(), ["a dragon rises"], 4, None)
    pre_p044 = {"scan_depth", "scan_mode", "scan_external_context",
                "scan_window", "token_budget", "tokens_used", "seed",
                "roll_context", "entries"}
    assert pre_p044 <= set(preview)
    assert set(preview) == pre_p044 | {"token_account"}
    expected_row_keys = {
        "entry_id", "name", "enabled", "constant", "vectorised",
        "activation_kind", "matched_primary", "matched_secondary",
        "vector_score", "external_indices", "via", "depth", "content", "status",
        "tokens", "discard_reason", "inclusion_group", "group_weight",
        "group_winner_id", "probability", "probability_roll", "position",
        "role", "injection_depth"}
    for row in preview["entries"]:
        assert set(row) == expected_row_keys

# ------------------------------------------------------------- layered

def _merged_preview():
    rows = [
        {"entry_id": "r1", "status": "included", "tokens": 10,
         "discard_reason": None, "lorebook_id": "book1", "scope": "global"},
        {"entry_id": "r2", "status": "included", "tokens": 10,
         "discard_reason": None, "lorebook_id": "book1", "scope": "global"},
        {"entry_id": "r3", "status": "not_triggered", "tokens": None,
         "discard_reason": None, "lorebook_id": "book1", "scope": "global"},
    ]
    return {"scan_depth": 4, "token_budget": None, "tokens_used": 20,
            "entries": rows,
            "token_account": account_from_rows(
                [dict(r) for r in rows], token_budget=None).to_dict()}

def test_layer_budget_rebuilds_token_account():
    preview = _merged_preview()
    _apply_layer_budget(preview, 10)
    rows = {r["entry_id"]: r for r in preview["entries"]}
    assert rows["r1"]["status"] == "included"
    assert rows["r2"]["status"] == "discarded"
    assert rows["r2"]["discard_reason"] == "scope_over_budget"
    assert preview["tokens_used"] == 10
    account = preview["token_account"]
    assert account["tokens_used"] == 10
    assert account["token_budget"] == 10
    assert account["budget_remaining"] == 0
    assert account["by_status"]["included"] == {"count": 1, "tokens": 10, "spent": 10}
    assert account["by_status"]["discarded"] == {"count": 1, "tokens": 10, "spent": 0}

def test_layer_zero_budget_account():
    preview = _merged_preview()
    _apply_layer_budget(preview, 0)
    assert preview["tokens_used"] == 0
    assert all(r["status"] != "included" for r in preview["entries"])
    account = preview["token_account"]
    assert account["token_budget"] == 0
    assert account["tokens_used"] == 0
    assert account["budget_remaining"] == 0

# ------------------------------------------------ inspector (s215 harness)

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

def seed_world(client, token_budget=None):
    card = copy.deepcopy(V2_CARD)
    card["name"] = "Bryn"
    card["description"] = "A smith of the harbor town."
    character = client.post("/api/v1/characters", json={"card": card}).json()["id"]
    book = client.post("/api/v1/lorebooks",
                       json={"name": "World", "token_budget": token_budget}).json()
    entries = {}
    for name, content, keys in (
        ("Harbor", "The harbor freezes hard in deep winter months.", ["harbor"]),
        ("Distant", "Far away and never mentioned here at all.", ["zzz-absent"]),
        ("Anchor", "Always present anchor entry text.", []),
    ):
        created = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries",
            json={"name": name, "content": content, "keys": keys,
                  "constant": name == "Anchor"})
        entries[name] = created.json()["id"]
    return character, book["id"], entries

def test_inspector_lore_account_reconciles(tmp_path, monkeypatch):
    # Inspector path (not compose-level fallback): the API result
    # IS inspect_prompt's dict, lore_account included.
    client = make_client(tmp_path, monkeypatch)
    character, book_id, _entries = seed_world(client)
    response = client.post("/api/v1/debug/prompt-inspect", json={
        "character_id": character, "lorebook_ids": [book_id],
        "messages": ["Down at the harbor today."]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert "lore_account" in result
    expected = sum(s["tokens"] for s in result["slots"]
                   if s["kind"] in ("lore_before", "lore_after")
                   and s["status"] == "included")
    assert expected > 0  # Harbor + Anchor really included: non-trivial
    account = result["lore_account"]
    assert account["tokens_used"] == expected
    assert account["tokens_used"] == sum(
        e["tokens"] for e in account["entries"] if e["status"] == "included")
    assert sum(v["tokens_used"] for v in account["by_provenance"].values()) == expected

# ------------------------------------------- composer tight budget

def test_composer_discard_account_excludes_over_budget_lore():
    small_content = "tiny lore text"
    big_content = "B" * 400
    def row_for(content):
        return {"injection_depth": None, "position": "before_char",
                "role": "system", "content": content, "via": "key",
                "matched_primary": ["dragon"]}
    slots = [
        make_slot("main_system", "system", MAIN_SYSTEM_TEXT,
                  required=True, id="system/main"),
        _lore_slot(row_for(big_content), "lore/big", "lorebook:B"),
        _lore_slot(row_for(small_content), "lore/small", "lorebook:B"),
    ]
    main_tokens = estimate_tokens(MAIN_SYSTEM_TEXT)
    small_tokens = estimate_tokens(small_content)
    big_tokens = estimate_tokens(big_content)
    reserve = 10
    context_limit = reserve + main_tokens + small_tokens + 10
    composed = compose(slots, context_limit=context_limit,
                       reserve_response=reserve)
    trace = trace_to_dict(build_trace(composed, slots))
    by_id = {s["slot_id"]: s for s in trace["slots"]}
    assert by_id["lore/big"]["status"] == "discarded"
    assert by_id["lore/big"]["reason"] == "over_input_budget"
    assert by_id["lore/small"]["status"] == "included"
    account = account_from_trace(trace)
    assert account["tokens_used"] == small_tokens
    assert account["discarded_tokens"] == big_tokens
    assert big_tokens not in (account["tokens_used"],)

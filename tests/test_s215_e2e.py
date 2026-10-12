"""S215 acceptance: Campaign II integration E2E + hardening.

One scenario drives the whole campaign surface end to end: lorebook CRUD
-> keyword scan (S202) -> activation with recursion + sticky (S203) ->
budget packing (S204) -> prompt composition with depth injection (S205,
S206) counted exactly (S214) -> preset compat filtering (S207, S208) ->
group turn over shared state (S210) -> generation session lifecycle
(S209). Hardening: composer invariant sweep, regex-hostile scan keys,
and lore recursion cycles.
"""

import random

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.generation.compat import filter_for_backend
from runmal.generation.modes import GenerationSession, Mode
from runmal.groupchat.core import GroupChat, Participant, Strategy
from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.scan import ScanEntry, scan_entries
from runmal.prompt import compose, make_slot
from runmal.prompt.slots import Slot
from runmal.prompt import baseline_order
from runmal.tokens import TokenQuality


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def word_tokenizer(text: str) -> int:
    return max(1, len(text.split()))


FORD = "The ford is shallow after dry weeks and watched by ravens."
OATH = "An oath sworn at running water binds twice. Recall: {{lore:Ford}}"
WYRD = "Wyrd weaves as it wills."


def seed_lorebook(client) -> dict:
    book = client.post(
        "/api/v1/lorebooks",
        json={"name": "Northlands", "scan_depth": 4, "token_budget": 60},
    ).json()
    entries = {}
    for payload in (
        {"name": "Ford", "content": FORD, "keys": ["ford"], "priority": 90},
        {"name": "Oath", "content": OATH, "keys": ["oath"],
         "secondary_keys": ["ford"], "priority": 80, "sticky_prompts": 2},
        {"name": "Wyrd", "content": WYRD, "constant": True, "priority": 10},
    ):
        entry = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries", json=payload
        ).json()
        entries[entry["name"]] = entry
    return entries


def test_campaign_ii_end_to_end(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    entries = seed_lorebook(client)

    # -- preset + connection ride along (S207/S211) -----------------------
    preset = client.post(
        "/api/v1/presets",
        json={"name": "saga", "params": {
            "temperature": 0.8, "max_tokens": 400,
            "repetition_penalty": 1.05, "frequency_penalty": 0.3}},
    )
    assert preset.status_code == 201
    conn = client.post(
        "/api/v1/connections",
        json={"name": "laptop", "backend": "ollama",
              "base_url": "http://localhost:11434", "model": "llama3"},
    )
    assert conn.status_code == 201

    # -- scan (S202) ------------------------------------------------------
    messages = ["We ride at dawn.", "At the ford, I swear an oath."]
    scan_view = [
        ScanEntry(
            id=e["id"], constant=e["constant"], keys=tuple(e["keys"]),
            secondary_keys=tuple(e["secondary_keys"]),
        )
        for e in entries.values()
    ]
    hits = scan_entries(scan_view, messages, scan_depth=4)
    hit_ids = {h.entry_id for h in hits}
    assert hit_ids == {entries["Ford"]["id"], entries["Oath"]["id"]}

    # -- activation: recursion + sticky (S203) ----------------------------
    act_view = [
        ActivatableEntry(
            id=e["id"], name=e["name"], content=e["content"],
            constant=e["constant"], sticky_prompts=e["sticky_prompts"],
        )
        for e in entries.values()
    ]
    result = activate(act_view, hit_ids)
    by_name = {a.entry_id: a for a in result.activations}
    assert entries["Wyrd"]["id"] in by_name  # constant
    oath = by_name[entries["Oath"]["id"]]
    assert oath.via == "key"
    assert FORD in oath.content  # {{lore:Ford}} expanded by recursion
    # next tick, no hits: Oath persists via sticky
    result2 = activate(act_view, set(), states=result.states)
    vias = {a.entry_id: a.via for a in result2.activations}
    assert vias.get(entries["Oath"]["id"]) == "sticky"
    # Ford returns too -- pulled in by Oath's {{lore:Ford}} reference
    assert vias.get(entries["Ford"]["id"]) == "reference"

    # -- budget (S204) ------------------------------------------------------
    candidates = [
        BudgetCandidate(a.entry_id, a.content, priority=50)
        for a in result.activations
    ]
    packed = resolve_budget(candidates, token_budget=60, seed=7)
    assert packed.tokens_used <= 60
    assert {b.entry_id for b in packed.included} | {
        d.entry_id for d in packed.discarded
    } == {c.entry_id for c in candidates}

    # -- compose (S205 + S206), exact counts (S214) -------------------------
    lore_text = "\n".join(
        next(a.content for a in result.activations if a.entry_id == b.entry_id)
        for b in packed.included
    )
    slots = [
        make_slot("main_system", "system", "Speak as the saga demands.",
                  id="sys", required=True),
        make_slot("lore_before", "system", lore_text, id="lore", priority=50),
        Slot(id="history", kind="history", role="user",
             order=baseline_order("history"), splittable=True,
             parts=tuple(messages)),
        make_slot("authors_note", "system", "Hold to the oath.",
                  id="note", depth=1),
    ]
    composed = compose(slots, context_limit=200, reserve_response=40,
                       counter=word_tokenizer)
    m = composed.manifest
    assert m.count_quality == TokenQuality.EXACT
    assert m.total_input_tokens <= m.input_budget
    slot_ids = [msg.slot_id for msg in composed.messages]
    assert slot_ids.index("note") == len(slot_ids) - 2  # depth 1 from end

    # -- compat (S208) ------------------------------------------------------
    filtered = filter_for_backend(preset.json()["params"], "ollama")
    assert filtered.params["num_predict"] == 400
    assert ("max_tokens", "num_predict") in [
        (x.source, x.dest) for x in filtered.mapped
    ]
    assert [d.param for d in filtered.dropped] == ["frequency_penalty"]

    # -- group turn over shared state (S210) --------------------------------
    chat = GroupChat(participants=[
        Participant("c1", "Bryn", "Bryn the skald."),
        Participant("c2", "Una", "Una the healer."),
    ])
    chat.post_user("What happened at the ford, @Una?")
    replies = chat.run_turn(
        lambda p, prompt: f"{p.name} answers about {len(prompt)} prompt rows.",
        Strategy.MENTION,
    )
    assert [r.author for r in replies] == ["Una"]

    # -- session lifecycle (S209) -------------------------------------------
    session = GenerationSession(mode=Mode.NORMAL)
    prompt_rows = [{"role": msg.role, "content": msg.content}
                   for msg in composed.messages]
    session.compose(prompt_rows)
    session.begin()
    session.complete("At the ford I swore, and the ravens watched.")
    session.regenerate(prompt_rows)  # stable identity under regenerate
    session.begin()
    session.complete("At the ford I swore; the river remembers.")
    assert session.swipe(-1) is True
    role, text = session.commit()
    assert role == "assistant"
    assert "ravens watched" in text


# -- hardening -------------------------------------------------------------


def test_hardening_composer_invariant_sweep():
    rng = random.Random(215)
    for trial in range(60):
        slots = []
        for i in range(rng.randint(1, 8)):
            kind = rng.choice(
                ["main_system", "persona", "lore_before", "scenario",
                 "authors_note"]
            )
            slots.append(
                make_slot(kind, "system", "w " * rng.randint(1, 60),
                          id=f"s{i}", required=(i == 0))
            )
        slots.append(
            Slot(id="history", kind="history", role="user",
                 order=baseline_order("history"), splittable=True,
                 parts=tuple("h " * rng.randint(1, 20)
                             for _ in range(rng.randint(1, 6))))
        )
        limit = rng.randint(30, 300)
        result = compose(slots, context_limit=limit, reserve_response=5)
        m = result.manifest
        assert m.total_input_tokens <= m.input_budget, trial
        accounted = {u.slot_id for u in m.included} | {
            d.slot_id for d in m.discarded
        }
        assert accounted == {s.id for s in slots}, trial


def test_hardening_scan_regex_hostile_keys():
    entries = [
        ScanEntry(id="cpp", keys=("c++",), whole_word=False),
        ScanEntry(id="dot", keys=("a.b",), whole_word=False),
        ScanEntry(id="paren", keys=("(oath)",), whole_word=False),
    ]
    hits = scan_entries(entries, ["I code c++ and a.b daily (oath) yes"], 4)
    assert {h.entry_id for h in hits} == {"cpp", "dot", "paren"}


def test_hardening_lore_recursion_cycle_terminates():
    a = ActivatableEntry(id="a", name="Alpha", content="A {{lore:Beta}}",
                         constant=True)
    b = ActivatableEntry(id="b", name="Beta", content="B {{lore:Alpha}}",
                         constant=True)
    result = activate([a, b], set())
    assert result.activations  # terminates with output, no hang
    for act in result.activations:
        assert act.depth <= 5

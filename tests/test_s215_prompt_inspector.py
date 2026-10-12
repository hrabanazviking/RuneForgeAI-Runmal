"""Roadmap S215 acceptance: prompt inspector UI.

The inspector composes from stored data and returns the S214 trace;
from the trace alone a user can answer "why was this injected /
discarded?" -- an entry that fired shows its trigger, an entry cut by
the lore budget shows the lore-stage reason, an entry whose key never
appeared shows not_triggered, and an entry cut by the composer shows
the composer reason. The page renders ledger + per-slot why rows.
"""

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

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
    book = client.post(
        "/api/v1/lorebooks", json={"name": "World", "token_budget": token_budget}
    ).json()
    entries = {}
    for name, content, keys in (
        ("Harbor", "The harbor freezes hard in deep winter months.", ["harbor"]),
        ("Distant", "Far away and never mentioned here at all.", ["zzz-absent"]),
        ("Anchor", "Always present anchor entry text.", []),
    ):
        created = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries",
            json={"name": name, "content": content, "keys": keys, "constant": name == "Anchor"},
        )
        entries[name] = created.json()["id"]
    return character, book["id"], entries


def test_inspector_answers_why(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    character, book_id, entries = seed_world(client)
    response = client.post(
        "/api/v1/debug/prompt-inspect",
        json={
            "character_id": character,
            "lorebook_ids": [book_id],
            "messages": ["Down at the harbor today."],
        },
    )
    assert response.status_code == 200, response.text
    trace = response.json()
    by_id = {s["slot_id"]: s for s in trace["slots"]}

    harbor = by_id[f"lore/{entries['Harbor']}"]
    assert harbor["status"] == "included"
    assert harbor["trigger"] == "harbor"  # why injected: this key fired

    anchor = by_id[f"lore/{entries['Anchor']}"]
    assert anchor["status"] == "included"
    assert anchor["trigger"] == "constant"

    distant = by_id[f"lore/{entries['Distant']}"]
    assert distant["status"] == "discarded"
    assert distant["reason"] == "not_triggered"  # why not: key never hit

    ledger = trace["ledger"]
    assert ledger["total_input_tokens"] <= ledger["input_budget"]
    assert trace["lore_triggers"], "lore trigger summary present"


def test_inspector_lore_budget_discard_reason(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    _, book_id, entries = seed_world(client, token_budget=10)
    # Budget of 10 tokens fits only one of the two activated entries;
    # priority order decides, and the loser must say lore:over_budget.
    response = client.post(
        "/api/v1/debug/prompt-inspect",
        json={"lorebook_ids": [book_id], "messages": ["harbor"]},
    )
    assert response.status_code == 200
    by_id = {s["slot_id"]: s for s in response.json()["slots"]}
    reasons = {s["reason"] for s in by_id.values() if s["status"] == "discarded"}
    assert "lore:over_budget" in reasons


def test_inspector_unknown_ids_404(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/debug/prompt-inspect",
        json={"lorebook_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 404


def test_inspector_page_renders(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/inspector")
    assert page.status_code == 200
    for element_id in (
        "inspector-main",
        "inspect-form",
        "inspect-character",
        "inspect-lorebook",
        "inspect-messages",
        "ledger-summary",
        "trace-table",
        "trace-rows",
    ):
        assert f'id="{element_id}"' in page.text, element_id
    assert "/static/inspector.js" in page.text

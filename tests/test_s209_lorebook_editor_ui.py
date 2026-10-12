"""Roadmap S209 acceptance: lorebook editor UI + activation preview.

The editor page ships an activation-preview panel backed by
``POST /api/v1/lorebooks/{book_id}/preview``. The preview must match the
server activation engine: these tests run the S202 scan / S203 activation /
S204 budget pipeline directly over the same entry data and require the
endpoint's per-entry verdicts to equal the engine's.
"""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.scan import ScanEntry, scan_entries

MESSAGES = [
    "We sailed into the harbor at dawn.",
    "The dragon sleeps under the mountain.",
]

ENTRIES = [
    # name, kwargs
    ("Tide", dict(content="The tide is eternal.", constant=True)),
    ("Harbor", dict(content="A safe harbor.", keys=["harbor"])),
    (
        "Dragon",
        dict(
            content="Dragons hoard gold.",
            keys=["dragon"],
            secondary_keys=["mountain"],
        ),
    ),
    (
        "Gated",
        dict(content="Winter only.", keys=["harbor"], secondary_keys=["winter"]),
    ),
    ("Ghost", dict(content="Boo.", keys=["specter"], enabled=False)),
    ("Silent", dict(content="Nothing.", keys=["zzz-absent"])),
    ("DeepLore", dict(content="Deep lore text.", keys=["never-matched"])),
    (
        "RefSource",
        dict(content="Dawn breaks. {{lore:DeepLore}}", keys=["dawn"]),
    ),
]


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_book_with_entries(client, **book_kwargs):
    book = client.post("/api/v1/lorebooks", json={"name": "Preview Book", **book_kwargs})
    assert book.status_code == 201, book.text
    book = book.json()
    for name, kwargs in ENTRIES:
        resp = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json={"name": name, **kwargs})
        assert resp.status_code == 201, resp.text
    return book


def _engine_expectation(entry_dicts, messages, scan_depth, token_budget):
    """Run the server engine directly over API-shaped entry data."""
    views = []
    for d in entry_dicts:
        views.append(
            SimpleNamespace(
                id=d["id"],
                name=d["name"],
                content=d["content"],
                enabled=d["enabled"],
                constant=d["constant"],
                keys_json=json.dumps(d["keys"]),
                secondary_keys_json=json.dumps(d["secondary_keys"]),
                whole_word=d["whole_word"],
                case_sensitive=d["case_sensitive"],
                sticky_prompts=d["sticky_prompts"],
                cooldown_prompts=d["cooldown_prompts"],
                delay_prompts=d["delay_prompts"],
                priority=d["priority"],
            )
        )
    hits = scan_entries([ScanEntry.from_orm(v) for v in views], messages, scan_depth)
    hit_by_id = {h.entry_id: h for h in hits}
    result = activate([ActivatableEntry.from_orm(v) for v in views], set(hit_by_id))
    act_by_id = {a.entry_id: a for a in result.activations}
    by_id = {v.id: v for v in views}
    budget = resolve_budget(
        [
            BudgetCandidate(a.entry_id, a.content, by_id[a.entry_id].priority)
            for a in result.activations
        ],
        token_budget,
    )
    included = {b.entry_id for b in budget.included}
    discarded = {d.entry_id: d for d in budget.discarded}
    expected = {}
    for v in views:
        act = act_by_id.get(v.id)
        if not v.enabled:
            status = "disabled"
        elif act is None:
            status = "not_triggered"
        elif v.id in included:
            status = "included"
        else:
            status = "discarded"
        expected[v.id] = {
            "status": status,
            "via": act.via if act else None,
            "depth": act.depth if act else None,
            "content": act.content if act else None,
            "matched_primary": list(hit_by_id[v.id].matched_primary) if v.id in hit_by_id else [],
            "matched_secondary": list(hit_by_id[v.id].matched_secondary)
            if v.id in hit_by_id
            else [],
            "discard_reason": discarded[v.id].reason if v.id in discarded else None,
        }
    return expected, budget.tokens_used


def test_preview_requires_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = make_book_with_entries(client)
    client.headers.pop("Authorization")
    resp = client.post(f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": MESSAGES})
    assert resp.status_code == 401


def test_preview_unknown_book_404(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/lorebooks/nope/preview", json={"messages": MESSAGES})
    assert resp.status_code == 404


def test_preview_matches_server_engine(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = make_book_with_entries(client)
    entries = client.get(f"/api/v1/lorebooks/{book['id']}/entries").json()

    resp = client.post(f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": MESSAGES})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["book_id"] == book["id"]
    assert payload["scan_depth"] == book["scan_depth"]  # book default applied
    assert payload["token_budget"] is None

    expected, tokens_used = _engine_expectation(entries, MESSAGES, 4, None)
    assert payload["tokens_used"] == tokens_used
    assert len(payload["entries"]) == len(entries)
    for row in payload["entries"]:
        want = expected[row["entry_id"]]
        assert row["status"] == want["status"], row
        assert row["via"] == want["via"], row
        assert row["depth"] == want["depth"], row
        assert row["content"] == want["content"], row
        assert row["matched_primary"] == want["matched_primary"], row
        assert row["matched_secondary"] == want["matched_secondary"], row
        assert row["discard_reason"] == want["discard_reason"], row

    by_name = {r["name"]: r for r in payload["entries"]}
    assert by_name["Tide"]["via"] == "constant"
    assert by_name["Tide"]["status"] == "included"
    assert by_name["Harbor"]["via"] == "key"
    assert by_name["Harbor"]["matched_primary"] == ["harbor"]
    assert by_name["Dragon"]["matched_secondary"] == ["mountain"]
    # Primary hit but missing secondary gate: never triggers.
    assert by_name["Gated"]["status"] == "not_triggered"
    assert by_name["Ghost"]["status"] == "disabled"
    assert by_name["Silent"]["status"] == "not_triggered"
    # {{lore:...}} reference pulls DeepLore in at depth 1, content inlined.
    assert by_name["DeepLore"]["via"] == "reference"
    assert by_name["DeepLore"]["depth"] == 1
    assert "Deep lore text." in by_name["RefSource"]["content"]


def test_preview_uses_book_budget_default(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = make_book_with_entries(client, token_budget=3)
    resp = client.post(f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": MESSAGES})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["token_budget"] == 3
    discarded = [r for r in payload["entries"] if r["status"] == "discarded"]
    assert discarded, payload
    assert all(r["discard_reason"] == "over_budget" for r in discarded)
    assert payload["tokens_used"] <= 3


def test_preview_scan_depth_override(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = make_book_with_entries(client)
    # Scan depth 1 sees only the last message: the harbor key (message 0)
    # falls out of the window; the dragon (message 1) still triggers.
    resp = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": MESSAGES, "scan_depth": 1},
    )
    assert resp.status_code == 200, resp.text
    by_name = {r["name"]: r for r in resp.json()["entries"]}
    assert by_name["Harbor"]["status"] == "not_triggered"
    assert by_name["Dragon"]["status"] == "included"


def test_editor_page_has_preview_panel(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/lorebooks")
    assert page.status_code == 200
    for marker in (
        'id="preview-panel"',
        'id="p-messages"',
        'id="p-run"',
        'id="p-results"',
        'id="p-summary"',
    ):
        assert marker in page.text
    js = client.get("/static/lorebooks.js")
    assert js.status_code == 200
    assert "/preview" in js.text

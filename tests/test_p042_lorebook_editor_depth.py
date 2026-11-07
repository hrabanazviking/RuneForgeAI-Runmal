"""P-042 acceptance: lorebook editor depth.

The UI must reach every field the engine honours -- no
engine-only settings. The core proof is a census: the engine's
field set is derived independently (SQLAlchemy models, engine
vocabularies, service dicts, router models) and every field must
appear in the P-042 census (runmal.lorebooks.editor), in the API
shape that carries it, and in the shipped editor page + JS.
Round-trips then prove the reachability is real, not cosmetic:
every field can be set to a non-default value through the API
the editor drives and read back unchanged. The preview panel's
controls are proven against the engine, including the P-031
recursive-scan opt-in this slice wires through the API.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Lorebook, LorebookScope, LoreEntry
from runmal.lorebooks import editor as census
from runmal.lorebooks.groups import DEFAULT_GROUP_WEIGHT  # noqa: F401  (vocab anchor)
from runmal.lorebooks.logic import SELECTIVE_LOGICS
from runmal.lorebooks.placement import VALID_POSITIONS, VALID_ROLES
from runmal.lorebooks.router import (
    EntryCreate,
    EntryUpdate,
    LorebookCreate,
    LorebookUpdate,
    PreviewRequest,
    ScopeAssign,
)
from runmal.lorebooks.scopes import SCOPE_KINDS
from runmal.lorebooks.service import entry_to_dict, lorebook_to_dict
from runmal.lorebooks.scopes import scope_to_dict
from runmal.lorebooks.states import ACTIVATION_KINDS
from runmal.lorebooks.windows import SCAN_MODES


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _columns(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


# -- Census completeness: derived engine fields vs the census -------

def test_census_covers_every_book_model_field() -> None:
    engine_fields = _columns(Lorebook) - {"id", "user_id", "created_at"}
    assert engine_fields == set(census.field_names("book"))


def test_census_covers_every_entry_model_field() -> None:
    raw = _columns(LoreEntry) - {
        "id", "lorebook_id", "user_id", "created_at", "updated_at",
    }
    engine_fields = {
        {"keys_json": "keys", "secondary_keys_json": "secondary_keys"}.get(c, c)
        for c in raw
    }
    authored = {
        f.name for f in census.ENTRY_FIELDS if f.kind != "derived"
    }
    assert engine_fields == authored
    # The one derived field is the P-035 activation kind, shown read-only.
    derived = {f.name for f in census.ENTRY_FIELDS if f.kind == "derived"}
    assert derived == {"activation_kind"}


def test_census_covers_every_scope_model_field() -> None:
    engine_fields = _columns(LorebookScope) - {
        "id", "user_id", "lorebook_id", "created_at", "updated_at",
    }
    assert engine_fields == set(census.field_names("scope"))


def test_census_covers_every_preview_control() -> None:
    assert set(PreviewRequest.model_fields) == set(census.field_names("preview"))
    # The preview engine itself honours exactly these controls.
    import inspect

    from runmal.lorebooks.preview import preview_activation

    params = set(inspect.signature(preview_activation).parameters)
    engine_controls = {
        "seed", "roll_context", "recursive_scan", "max_recursion_depth",
        "vector_hit_ids", "vector_threshold", "vector_max_entries",
        "scan_mode", "scan_external_context", "external_context",
    }
    assert engine_controls <= params
    assert engine_controls <= set(census.field_names("preview"))


def test_census_select_vocabularies_match_engine() -> None:
    def field(surface, name):
        return next(f for f in census.SURFACES[surface] if f.name == name)

    assert set(field("entry", "position").options) == set(VALID_POSITIONS)
    assert set(field("entry", "role").options) == set(VALID_ROLES)
    assert set(field("entry", "selective_logic").options) == set(SELECTIVE_LOGICS)
    assert set(field("book", "scan_mode").options) == set(SCAN_MODES)
    assert set(field("preview", "scan_mode").options) == set(SCAN_MODES)
    assert set(field("scope", "scope_kind").options) == set(SCOPE_KINDS)
    assert set(field("entry", "activation_kind").options) == set(ACTIVATION_KINDS)


# -- API + service reachability --------------------------------------

def test_every_census_field_is_in_its_api_models() -> None:
    models = {
        "LorebookCreate": LorebookCreate, "LorebookUpdate": LorebookUpdate,
        "EntryCreate": EntryCreate, "EntryUpdate": EntryUpdate,
        "ScopeAssign": ScopeAssign, "PreviewRequest": PreviewRequest,
    }
    for fields in census.SURFACES.values():
        for f in fields:
            if not f.api_model:
                continue  # derived display field
            assert f.name in models[f.api_model].model_fields, f
    # Update shapes carry the full authored set too (no create-only fields).
    for f in census.ENTRY_FIELDS:
        if f.kind != "derived":
            assert f.name in EntryUpdate.model_fields, f
    for f in census.BOOK_FIELDS:
        assert f.name in LorebookUpdate.model_fields, f


def test_service_dicts_carry_every_field() -> None:
    now = datetime.now(UTC)
    book = Lorebook(
        id="b1", user_id="u1", name="B", description="d", scan_depth=7,
        token_budget=99, scan_mode="whole_chat", scan_external_context=True,
        created_at=now,
    )
    book_dict = lorebook_to_dict(book, 3)
    for name in census.field_names("book"):
        assert name in book_dict, name
    entry = LoreEntry(
        id="e1", lorebook_id="b1", user_id="u1", name="E", content="c",
        keys_json='["k"]', secondary_keys_json='["s"]',
        selective_logic="not_all", inclusion_group="g", group_weight=5,
        probability=42, priority=9, position="at_depth", depth=2,
        role="user", enabled=False, constant=False, vectorised=True,
        case_sensitive=True, whole_word=False, sticky_prompts=1,
        cooldown_prompts=2, delay_prompts=3, created_at=now, updated_at=now,
    )
    entry_dict = entry_to_dict(entry)
    for name in census.field_names("entry"):
        assert name in entry_dict, name
    assert entry_dict["activation_kind"] == "vectorised"
    scope = LorebookScope(
        id="s1", user_id="u1", lorebook_id="b1", scope_kind="chat",
        owner_id="c1", token_budget=12, position=4, created_at=now,
        updated_at=now,
    )
    scope_dict = scope_to_dict(scope)
    for name in census.field_names("scope"):
        assert name in scope_dict, name


def test_editor_schema_endpoint_serves_the_census(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/lorebooks/editor-schema")
    assert resp.status_code == 200, resp.text
    assert resp.json() == census.editor_schema()
    client.headers.pop("Authorization")
    assert client.get("/api/v1/lorebooks/editor-schema").status_code == 401


# -- UI reachability: the shipped page + JS ---------------------------

def _page_and_js(client):
    page = client.get("/lorebooks")
    assert page.status_code == 200
    js = client.get("/static/lorebooks.js")
    assert js.status_code == 200
    return page.text, js.text


def test_editor_page_has_an_element_for_every_census_field(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    html, _js = _page_and_js(client)
    for fields in census.SURFACES.values():
        for f in fields:
            assert f'id="{f.element_id}"' in html, f
            if f.kind == "select":
                for opt in f.options:
                    assert f'value="{opt}"' in html, (f, opt)


def test_editor_js_wires_every_census_field(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    _html, js = _page_and_js(client)
    for fields in census.SURFACES.values():
        for f in fields:
            # The element is read or written by the script...
            assert f'"{f.element_id}"' in js, f
            # ...and authored fields travel under their API name.
            if f.kind != "derived":
                assert f.name in js, f
    # Entry fields are both filled from API dicts and sent as payloads.
    for f in census.ENTRY_FIELDS:
        if f.kind != "derived":
            assert js.count(f.name) >= 2, f


# -- Round-trips: reachability is real --------------------------------

BOOK_PAYLOAD = {
    "name": "Deep Book", "description": "every knob", "scan_depth": 9,
    "token_budget": 4321, "scan_mode": "whole_chat",
    "scan_external_context": True,
}
BOOK_PAYLOAD_2 = {
    "name": "Deep Book II", "description": "turned", "scan_depth": 2,
    "token_budget": 77, "scan_mode": "depth", "scan_external_context": False,
}
ENTRY_PAYLOAD = {
    "name": "Full", "content": "all fields set", "keys": ["alpha"],
    "secondary_keys": ["beta"], "selective_logic": "not_all",
    "inclusion_group": "duel", "group_weight": 7, "probability": 42,
    "priority": 33, "position": "at_depth", "depth": 3, "role": "user",
    "enabled": False, "constant": False, "vectorised": True,
    "case_sensitive": True, "whole_word": False, "sticky_prompts": 4,
    "cooldown_prompts": 5, "delay_prompts": 6,
}
ENTRY_PAYLOAD_2 = {
    "name": "Full II", "content": "turned again", "keys": ["gamma"],
    "secondary_keys": [], "selective_logic": "and_all",
    "inclusion_group": "", "group_weight": 100, "probability": 100,
    "priority": 100, "position": "after_char", "depth": None,
    "role": "assistant", "enabled": True, "constant": True,
    "vectorised": False, "case_sensitive": False, "whole_word": True,
    "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
}


def test_book_round_trip_every_field(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/lorebooks", json=BOOK_PAYLOAD)
    assert resp.status_code == 201, resp.text
    book = resp.json()
    for key, want in BOOK_PAYLOAD.items():
        assert book[key] == want, key
    resp = client.patch(f"/api/v1/lorebooks/{book['id']}", json=BOOK_PAYLOAD_2)
    assert resp.status_code == 200, resp.text
    for key, want in BOOK_PAYLOAD_2.items():
        assert resp.json()[key] == want, key


def test_entry_round_trip_every_field(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    resp = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json=ENTRY_PAYLOAD)
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    for key, want in ENTRY_PAYLOAD.items():
        assert entry[key] == want, key
    assert entry["activation_kind"] == "vectorised"
    resp = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{entry['id']}",
        json=ENTRY_PAYLOAD_2,
    )
    assert resp.status_code == 200, resp.text
    for key, want in ENTRY_PAYLOAD_2.items():
        assert resp.json()[key] == want, key
    assert resp.json()["activation_kind"] == "constant"
    got = client.get(f"/api/v1/lorebooks/{book['id']}/entries/{entry['id']}")
    for key, want in ENTRY_PAYLOAD_2.items():
        assert got.json()[key] == want, key


def test_scope_round_trip_via_editor_api(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "Scoped"}).json()
    card = {
        "name": "Sigrun", "description": "A test seer.",
        "personality": "Calm.", "scenario": "A test hall.",
        "first_mes": "Hail!", "mes_example": "", "creator_notes": "",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "test",
        "extensions": {},
    }
    char = client.post("/api/v1/characters", json={"card": card})
    assert char.status_code in (200, 201), char.text
    payload = {
        "scope_kind": "character", "owner_id": char.json()["id"],
        "token_budget": 250, "position": 2,
    }
    resp = client.put(f"/api/v1/lorebooks/{book['id']}/scope", json=payload)
    assert resp.status_code == 201, resp.text
    for key, want in payload.items():
        assert resp.json()[key] == want, key
    listed = client.get(f"/api/v1/lorebooks/{book['id']}/scopes")
    assert listed.status_code == 200
    assert [s["scope_kind"] for s in listed.json()["scopes"]] == ["character"]
    removed = client.delete(
        f"/api/v1/lorebooks/{book['id']}/scope",
        params={"scope_kind": "character", "owner_id": payload["owner_id"]},
    )
    assert removed.status_code == 200, removed.text
    listed = client.get(f"/api/v1/lorebooks/{book['id']}/scopes")
    assert listed.json()["scopes"] == []


# -- Preview controls reach the engine --------------------------------

def _recursion_book(client):
    book = client.post("/api/v1/lorebooks", json={"name": "Rec"}).json()
    a = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "A", "content": "the beta vault opens", "keys": ["alpha"]},
    ).json()
    b = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "B", "content": "deep lore", "keys": ["beta"]},
    ).json()
    return book, a, b


def test_preview_recursive_scan_now_reachable(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book, _a, _b = _recursion_book(client)
    plain = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": ["alpha rises"]}
    )
    assert plain.status_code == 200, plain.text
    by_name = {r["name"]: r for r in plain.json()["entries"]}
    assert by_name["B"]["status"] == "not_triggered"
    rec = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["alpha rises"], "recursive_scan": True},
    )
    assert rec.status_code == 200, rec.text
    payload = rec.json()
    assert payload["recursive_scan"] is True
    by_name = {r["name"]: r for r in payload["entries"]}
    assert by_name["B"]["status"] == "included"
    assert by_name["B"]["via"] == "recursive"
    capped = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={
            "messages": ["alpha rises"], "recursive_scan": True,
            "max_recursion_depth": 0,
        },
    )
    assert capped.status_code == 200, capped.text
    by_name = {r["name"]: r for r in capped.json()["entries"]}
    assert by_name["B"]["status"] == "not_triggered"


def test_preview_seed_roll_context_and_vector_hits(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "Vec"}).json()
    vec = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "V", "content": "vector lore", "vectorised": True},
    ).json()
    resp = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={
            "messages": ["nothing keyed here"], "seed": 7,
            "roll_context": "ctx-1", "vector_hit_ids": [vec["id"]],
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["seed"] == 7
    assert payload["roll_context"] == "ctx-1"
    by_name = {r["name"]: r for r in payload["entries"]}
    assert by_name["V"]["status"] == "included"
    assert by_name["V"]["via"] == "vector"

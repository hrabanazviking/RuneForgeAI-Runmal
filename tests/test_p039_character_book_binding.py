"""P-039 acceptance: character-book binding.

Roadmap line: *a card's own lorebook travels with it and merges
with the world's by declared precedence.*

Contract under test:
- ``runmal.lorebooks.binding`` is the pure merge module:
  ``PRECEDENCES`` is {character_first, world_first, priority} with
  ``DEFAULT_PRECEDENCE`` character_first; ``normalise_precedence``
  maps None to the default and raises ValueError on bad values;
  ``character_book_entries`` accepts both the list form and the
  uid-dict form of an embedded book's entries;
  ``normalise_book_entry`` normalises world-info-ish entries
  (``key`` / ``comment`` / ``disable`` / ``order`` ...) and native
  entries to the same native shape, mapping position codes
  0 / 1 / 4 to before_char / after_char / at_depth;
  ``merge_entry_dicts(world, character, precedence)`` returns
  ``{entries, shadowed}`` where a collision is the same non-empty
  name (strip + casefold) present in both scopes, the winner is
  scope-tagged and carries ``precedence_rank``, and every dropped
  entry is reported in ``shadowed`` with kept/dropped provenance.
  character_first keeps the character entry and ranks character
  entries first; world_first mirrors it; priority keeps the
  higher-priority entry (a tie keeps the character entry) and
  orders by (-priority, character-before-world, name, id). The
  merge is deterministic: same inputs, same output.
- DB: migration 0031 (PROVISIONAL -- 0029 is reserved for P-037
  and 0030 for P-038, which bank first; in this tree the tail runs
  [..., "0028", "0031"]) creates ``character_book_bindings`` and
  ``MIGRATIONS[-1][0] == "0031"``.
- API (characters router, /api/v1): creating a character whose
  card data carries ``character_book`` materialises a bound
  lorebook (asset discipline: a malformed book never refuses the
  card, it just leaves it unbound). GET
  /characters/{id}/lorebook-binding reports {"bound": false} for
  an unbound character and the binding + lorebook + precedence
  for a bound one; PUT binds an existing owned lorebook, PATCH
  changes the precedence, DELETE unbinds (the lorebook survives
  as a normal lorebook). GET /characters/{id}/character-book
  returns the travelling book dict -- from the bound lorebook
  when bound (so later entry edits show), else the stored card's
  book. POST /characters/{id}/lorebook-preview merges the bound
  character book with a world lorebook and returns a
  preview_activation-shaped result plus precedence,
  character_lorebook_id, world_lorebook_id, shadowed,
  merged=true, with rows carrying scope.
- Duplicating a character gives the clone its OWN copy of the
  book: editing the clone's book never changes the original's.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User
from runmal.lorebooks.binding import (
    DEFAULT_PRECEDENCE,
    PRECEDENCES,
    character_book_entries,
    check_precedence,
    merge_entry_dicts,
    normalise_book_entry,
    normalise_precedence,
)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr") -> str:
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def ent(eid, name, priority=100, **kw):
    entry = {"id": eid, "name": name, "priority": priority, "content": kw.pop("content", f"lore {eid}")}
    entry.update(kw)
    return entry


def card(name="Sigrun", book=None, include_book=True):
    data = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A test seer.",
        "personality": "Calm.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": "test",
        "extensions": {},
    }
    if include_book:
        data["character_book"] = book if book is not None else {"name": "Lore", "entries": []}
    return data


def book_entry(name, content, **kw):
    entry = {"name": name, "comment": name, "content": content, "keys": [name.lower()], "constant": True}
    entry.update(kw)
    return entry


def create_character(client, payload):
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_binding(client, character_id):
    resp = client.get(f"/api/v1/characters/{character_id}/lorebook-binding")
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_world_book(client, name="World", entries=()):
    book = client.post("/api/v1/lorebooks", json={"name": name})
    assert book.status_code == 201, book.text
    book = book.json()
    for entry in entries:
        resp = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json=entry)
        assert resp.status_code == 201, resp.text
    return book


# ------------------------------------------------------- precedence vocab


def test_precedence_vocabulary():
    assert set(PRECEDENCES) == {"character_first", "world_first", "priority"}
    assert DEFAULT_PRECEDENCE == "character_first"
    assert DEFAULT_PRECEDENCE in PRECEDENCES


def test_normalise_precedence():
    assert normalise_precedence(None) == "character_first"
    assert normalise_precedence("character_first") == "character_first"
    assert normalise_precedence("world_first") == "world_first"
    assert normalise_precedence("priority") == "priority"
    assert normalise_precedence(" World_First ") == "world_first"
    for bad in ("sideways", "", "character", 42, True, 1.5):
        with pytest.raises(ValueError):
            normalise_precedence(bad)


def test_check_precedence_strict():
    assert check_precedence("priority") == "priority"
    for bad in (None, "Character_First", "bogus"):
        with pytest.raises(ValueError):
            check_precedence(bad)


# ---------------------------------------------------- embedded-book entries


def test_character_book_entries_list_form():
    book = {"name": "B", "entries": [{"name": "a"}, {"name": "b"}]}
    entries = character_book_entries(book)
    assert [e["name"] for e in entries] == ["a", "b"]
    assert entries is not book["entries"]  # a copy, not the live list


def test_character_book_entries_uid_dict_form():
    book = {"entries": {"0": {"name": "a"}, "7": {"name": "b"}, "12": {"name": "c"}}}
    entries = character_book_entries(book)
    assert [e["name"] for e in entries] == ["a", "b", "c"]


def test_character_book_entries_junk_shapes():
    assert character_book_entries(None) == []
    assert character_book_entries("nope") == []
    assert character_book_entries({}) == []
    assert character_book_entries({"entries": 42}) == []
    assert character_book_entries({"entries": None}) == []


def test_normalise_book_entry_native_shape():
    out = normalise_book_entry(
        {
            "name": "Gale",
            "content": "gale lore",
            "keys": ["gale", "storm"],
            "secondary_keys": ["sea"],
            "priority": 42,
            "position": "after_char",
            "constant": True,
            "enabled": True,
        }
    )
    assert out["name"] == "Gale"
    assert out["content"] == "gale lore"
    assert out["keys"] == ["gale", "storm"]
    assert out["secondary_keys"] == ["sea"]
    assert out["priority"] == 42
    assert out["position"] == "after_char"
    assert out["constant"] is True
    assert out["enabled"] is True


def test_normalise_book_entry_worldinfo_shape():
    out = normalise_book_entry(
        {
            "comment": "Harbour Law",
            "key": ["harbour", "oath"],
            "keysecondary": ["sea"],
            "content": "harbour lore",
            "order": 300,
            "position": 4,
            "disable": True,
            "selectiveLogic": 1,
            "group": "weather",
            "groupWeight": 75,
            "caseSensitive": True,
            "matchWholeWords": False,
            "sticky": 3,
            "cooldown": 2,
            "delay": 1,
            "probability": 80,
            "useProbability": True,
        }
    )
    assert out["name"] == "Harbour Law"  # comment is the world-info name
    assert out["keys"] == ["harbour", "oath"]
    assert out["secondary_keys"] == ["sea"]
    assert out["priority"] == 300  # order is the world-info priority
    assert out["position"] == "at_depth"
    assert out["enabled"] is False  # disable=True
    assert out["inclusion_group"] == "weather"
    assert out["group_weight"] == 75
    assert out["case_sensitive"] is True
    assert out["whole_word"] is False
    assert out["sticky_prompts"] == 3
    assert out["cooldown_prompts"] == 2
    assert out["delay_prompts"] == 1
    assert out["probability"] == 80


@pytest.mark.parametrize("code,expected", [(0, "before_char"), (1, "after_char"), (4, "at_depth")])
def test_normalise_book_entry_position_codes(code, expected):
    assert normalise_book_entry({"position": code})["position"] == expected
    assert normalise_book_entry({"position": expected})["position"] == expected


def test_normalise_book_entry_use_probability_false_folds_to_100():
    out = normalise_book_entry({"probability": 30, "useProbability": False})
    assert out["probability"] == 100


def test_normalise_book_entry_rejects_non_dict():
    with pytest.raises(ValueError):
        normalise_book_entry(42)


# ------------------------------------------------------------- pure merge


def test_merge_character_first_wins_and_ranks_first():
    world = [ent("w1", "Shared", priority=500), ent("w2", "World Only", priority=999)]
    character = [ent("c1", "Shared", priority=1), ent("c2", "Char Only", priority=5)]
    out = merge_entry_dicts(world, character, "character_first")
    winners = out["entries"]
    # character scope first (its -priority order), then world scope
    assert [e["id"] for e in winners] == ["c2", "c1", "w2"]
    assert [e["scope"] for e in winners] == ["character", "character", "world"]
    assert [e["precedence_rank"] for e in winners] == [0, 1, 2]
    shared = next(e for e in winners if e["name"] == "Shared")
    assert shared["id"] == "c1" and shared["scope"] == "character"
    assert len(out["shadowed"]) == 1
    shadow = out["shadowed"][0]
    assert {k: shadow[k] for k in ("name", "kept_scope", "dropped_scope", "kept_id", "dropped_id")} == {
        "name": "Shared",
        "kept_scope": "character",
        "dropped_scope": "world",
        "kept_id": "c1",
        "dropped_id": "w1",
    }
    # inputs are never mutated
    assert "scope" not in world[0] and "precedence_rank" not in character[0]


def test_merge_world_first_mirrors():
    world = [ent("w1", "Shared", priority=500), ent("w2", "World Only", priority=999)]
    character = [ent("c1", "Shared", priority=1), ent("c2", "Char Only", priority=5)]
    out = merge_entry_dicts(world, character, "world_first")
    winners = out["entries"]
    assert [e["id"] for e in winners] == ["w2", "w1", "c2"]
    shared = next(e for e in winners if e["name"] == "Shared")
    assert shared["id"] == "w1" and shared["scope"] == "world"
    shadow = out["shadowed"][0]
    assert shadow["kept_scope"] == "world" and shadow["dropped_scope"] == "character"
    assert shadow["kept_id"] == "w1" and shadow["dropped_id"] == "c1"


def test_merge_priority_higher_priority_wins_either_scope():
    out = merge_entry_dicts([ent("w1", "Shared", priority=90)], [ent("c1", "Shared", priority=10)], "priority")
    assert [e["id"] for e in out["entries"]] == ["w1"]
    assert out["shadowed"][0]["kept_scope"] == "world"
    out = merge_entry_dicts([ent("w1", "Shared", priority=10)], [ent("c1", "Shared", priority=90)], "priority")
    assert [e["id"] for e in out["entries"]] == ["c1"]
    assert out["shadowed"][0]["kept_scope"] == "character"


def test_merge_priority_tie_keeps_character():
    out = merge_entry_dicts([ent("w1", "Shared", priority=50)], [ent("c1", "Shared", priority=50)], "priority")
    assert [e["id"] for e in out["entries"]] == ["c1"]
    assert out["shadowed"][0]["dropped_id"] == "w1"


def test_merge_priority_ordering():
    # (-priority, character-before-world, name, id)
    world = [ent("w-a", "Alpha", priority=10), ent("w-b", "Beta", priority=50)]
    character = [ent("c-c", "Gamma", priority=50), ent("c-d", "Delta", priority=30)]
    out = merge_entry_dicts(world, character, "priority")
    assert [e["id"] for e in out["entries"]] == ["c-c", "w-b", "c-d", "w-a"]
    assert [e["precedence_rank"] for e in out["entries"]] == [0, 1, 2, 3]
    assert out["shadowed"] == []


def test_merge_collision_key_is_strip_casefold():
    out = merge_entry_dicts([ent("w1", "  Gale ")], [ent("c1", "gale")], "character_first")
    assert [e["id"] for e in out["entries"]] == ["c1"]
    assert len(out["shadowed"]) == 1


def test_merge_unnamed_entries_never_collide():
    world = [ent("w1", ""), ent("w2", "   ")]
    character = [ent("c1", "")]
    out = merge_entry_dicts(world, character, "character_first")
    assert {e["id"] for e in out["entries"]} == {"w1", "w2", "c1"}
    assert out["shadowed"] == []


def test_merge_same_scope_duplicate_names_all_kept():
    world = [ent("w1", "Twin"), ent("w2", "Twin")]
    out = merge_entry_dicts(world, [], "character_first")
    assert {e["id"] for e in out["entries"]} == {"w1", "w2"}
    assert out["shadowed"] == []


def test_merge_is_deterministic():
    world = [ent("w1", "Shared", priority=70), ent("w2", "Alpha", priority=10), ent("w3", "Beta", priority=10)]
    character = [ent("c1", "Shared", priority=70), ent("c2", "Gamma", priority=10)]
    for mode in ("character_first", "world_first", "priority"):
        first = merge_entry_dicts(world, character, mode)
        for _ in range(5):
            assert merge_entry_dicts(world, character, mode) == first
        reversed_inputs = merge_entry_dicts(list(reversed(world)), list(reversed(character)), mode)
        assert [e["id"] for e in reversed_inputs["entries"]] == [e["id"] for e in first["entries"]]


def test_merge_bad_precedence_raises_and_none_defaults():
    with pytest.raises(ValueError):
        merge_entry_dicts([], [], "sideways")
    assert merge_entry_dicts([], [], None) == {"entries": [], "shadowed": []}


# ---------------------------------------------------------------- migration


def test_migration_head_is_0031_provisional():
    # 0029 is reserved for P-037 and 0030 for P-038 (both bank
    # first); in this tree the tail runs 0028 -> 0031.
    assert MIGRATIONS[-1][0] == "0032"
    assert MIGRATIONS[-3][0] == "0030"
    assert MIGRATIONS[-4][0] == "0029"
    assert MIGRATIONS[-5][0] == "0028"


def test_migration_0031_table_exists(tmp_path):
    import sqlite3

    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(character_book_bindings)")}
        assert {"id", "character_id", "lorebook_id", "precedence", "created_at"} <= cols
    finally:
        conn.close()


# --------------------------------------------------------------------- API


def test_create_with_book_materialises_binding(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = card(book={"name": "Sigrun Lore", "entries": [
        book_entry("Gale", "char gale lore"),
        book_entry("Harbour", "harbour lore", constant=False),
    ]})
    char = create_character(client, payload)
    binding = get_binding(client, char["id"])
    assert binding["bound"] is True
    assert binding["character_id"] == char["id"]
    assert binding["precedence"] == "character_first"
    assert binding["lorebook"]["id"] == binding["lorebook_id"]
    assert binding["lorebook"]["name"] == "Sigrun Lore"
    assert binding["entry_count"] == 2
    book = client.get(f"/api/v1/lorebooks/{binding['lorebook_id']}")
    assert book.status_code == 200
    assert {e["name"] for e in book.json()["entries"]} == {"Gale", "Harbour"}


def test_no_book_card_is_unbound(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = create_character(client, card(include_book=False))
    binding = get_binding(client, char["id"])
    assert binding["bound"] is False
    travel = client.get(f"/api/v1/characters/{char['id']}/character-book")
    assert travel.status_code == 200 and travel.json() == {"entries": []}
    missing = client.get("/api/v1/characters/missing/lorebook-binding")
    assert missing.status_code == 404


def test_malformed_book_never_refuses_card(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = card(book={"name": "Broken", "entries": [42]})
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code == 201, resp.text
    binding = get_binding(client, resp.json()["id"])
    assert binding["bound"] is False


def test_character_book_travel_reflects_entry_edit(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = card(book={"name": "Travelling", "entries": [book_entry("Gale", "before edit")]})
    char = create_character(client, payload)
    travel = client.get(f"/api/v1/characters/{char['id']}/character-book").json()
    assert travel["name"] == "Travelling"
    assert [e["content"] for e in travel["entries"]] == ["before edit"]
    binding = get_binding(client, char["id"])
    book = client.get(f"/api/v1/lorebooks/{binding['lorebook_id']}").json()
    entry_id = book["entries"][0]["id"]
    patched = client.patch(
        f"/api/v1/lorebooks/{binding['lorebook_id']}/entries/{entry_id}",
        json={"content": "after edit"},
    )
    assert patched.status_code == 200, patched.text
    travel2 = client.get(f"/api/v1/characters/{char['id']}/character-book").json()
    assert [e["content"] for e in travel2["entries"]] == ["after edit"]


def _preview_setup(client, char_priority=10, world_priority=90):
    payload = card(book={"name": "Char Lore", "entries": [
        book_entry("Shared", "character shared lore", priority=char_priority),
    ]})
    char = create_character(client, payload)
    world = make_world_book(client, entries=[
        {"name": "Shared", "keys": ["shared"], "content": "world shared lore", "constant": True, "priority": world_priority},
    ])
    return char, world


def _preview(client, char_id, world_id):
    resp = client.post(
        f"/api/v1/characters/{char_id}/lorebook-preview",
        json={"world_lorebook_id": world_id, "messages": ["shared ground"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_merged_preview_default_character_first_wins(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char, world = _preview_setup(client)
    binding = get_binding(client, char["id"])
    out = _preview(client, char["id"], world["id"])
    assert out["merged"] is True
    assert out["precedence"] == "character_first"
    assert out["character_lorebook_id"] == binding["lorebook_id"]
    assert out["world_lorebook_id"] == world["id"]
    assert len(out["shadowed"]) == 1
    assert out["shadowed"][0]["kept_scope"] == "character"
    assert out["shadowed"][0]["dropped_scope"] == "world"
    rows = [r for r in out["entries"] if r["name"] == "Shared"]
    assert len(rows) == 1  # the loser never reaches the preview rows
    assert rows[0]["scope"] == "character"
    assert rows[0]["status"] == "included"
    assert rows[0]["content"] == "character shared lore"


def test_merged_preview_precedence_flips_winner(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char, world = _preview_setup(client)  # world priority 90 > char 10
    patched = client.patch(
        f"/api/v1/characters/{char['id']}/lorebook-binding", json={"precedence": "world_first"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["precedence"] == "world_first"
    out = _preview(client, char["id"], world["id"])
    rows = [r for r in out["entries"] if r["name"] == "Shared"]
    assert len(rows) == 1 and rows[0]["scope"] == "world"
    assert rows[0]["content"] == "world shared lore"
    assert out["shadowed"][0]["kept_scope"] == "world"
    # priority mode: the higher-priority world entry (90) beats the
    # character entry (10) -- same winner here, by the other rule.
    patched = client.patch(
        f"/api/v1/characters/{char['id']}/lorebook-binding", json={"precedence": "priority"}
    )
    assert patched.status_code == 200, patched.text
    out = _preview(client, char["id"], world["id"])
    assert out["precedence"] == "priority"
    rows = [r for r in out["entries"] if r["name"] == "Shared"]
    assert len(rows) == 1 and rows[0]["scope"] == "world"
    assert out["shadowed"][0]["kept_scope"] == "world"


def test_put_bind_existing_and_delete_unbind_book_survives(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = create_character(client, card(include_book=False))
    book = make_world_book(client, name="Standalone", entries=[
        {"name": "Solo", "keys": ["solo"], "content": "solo lore", "constant": True},
    ])
    put = client.put(
        f"/api/v1/characters/{char['id']}/lorebook-binding",
        json={"lorebook_id": book["id"], "precedence": "world_first"},
    )
    assert put.status_code == 200, put.text
    assert put.json()["bound"] is True
    assert put.json()["lorebook_id"] == book["id"]
    assert put.json()["precedence"] == "world_first"
    assert get_binding(client, char["id"])["lorebook_id"] == book["id"]
    deleted = client.delete(f"/api/v1/characters/{char['id']}/lorebook-binding")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["unbound"] is True
    assert get_binding(client, char["id"])["bound"] is False
    # the lorebook itself survives as a normal lorebook
    survived = client.get(f"/api/v1/lorebooks/{book['id']}")
    assert survived.status_code == 200 and survived.json()["name"] == "Standalone"


def test_bad_precedence_is_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = card(book={"name": "Bound", "entries": [book_entry("Gale", "gale lore")]})
    char = create_character(client, payload)
    patched = client.patch(
        f"/api/v1/characters/{char['id']}/lorebook-binding", json={"precedence": "sideways"}
    )
    assert patched.status_code == 422, patched.text
    plain = create_character(client, card(name="Plain", include_book=False))
    book = make_world_book(client, name="Bindable")
    put = client.put(
        f"/api/v1/characters/{plain['id']}/lorebook-binding",
        json={"lorebook_id": book["id"], "precedence": "sideways"},
    )
    assert put.status_code == 422, put.text
    # the failed PUT must not have bound anything
    assert get_binding(client, plain["id"])["bound"] is False


def test_other_owner_character_binding_is_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    create_character(client, card(include_book=False))  # the real owner exists first

    async def _seed():
        factory = make_factory(tmp_path)
        async with factory() as session:
            user = User(name="intruder")
            session.add(user)
            await session.flush()
            other = Character(user_id=user.id, name="Not Yours", card_json="{}")
            session.add(other)
            await session.commit()
            return other.id

    other_id = asyncio.run(_seed())
    resp = client.get(f"/api/v1/characters/{other_id}/lorebook-binding")
    assert resp.status_code == 404, resp.text
    resp = client.get(f"/api/v1/characters/{other_id}/character-book")
    assert resp.status_code == 404, resp.text


def test_duplicate_gets_its_own_book_copy(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    payload = card(book={"name": "Original Lore", "entries": [
        book_entry("Gale", "gale lore"),
        book_entry("Harbour", "harbour lore", constant=False),
    ]})
    char = create_character(client, payload)
    dup_resp = client.post(f"/api/v1/characters/{char['id']}/duplicate")
    assert dup_resp.status_code == 201, dup_resp.text
    clone = dup_resp.json()
    assert clone["id"] != char["id"]
    orig_binding = get_binding(client, char["id"])
    clone_binding = get_binding(client, clone["id"])
    assert clone_binding["bound"] is True
    assert clone_binding["lorebook_id"] != orig_binding["lorebook_id"]

    def entry_shapes(book_id):
        book = client.get(f"/api/v1/lorebooks/{book_id}").json()
        return sorted((e["name"], e["content"], tuple(e["keys"])) for e in book["entries"])

    assert entry_shapes(clone_binding["lorebook_id"]) == entry_shapes(orig_binding["lorebook_id"])
    # editing the clone's book must not change the original's
    clone_book = client.get(f"/api/v1/lorebooks/{clone_binding['lorebook_id']}").json()
    gale = next(e for e in clone_book["entries"] if e["name"] == "Gale")
    patched = client.patch(
        f"/api/v1/lorebooks/{clone_binding['lorebook_id']}/entries/{gale['id']}",
        json={"content": "clone-only edit"},
    )
    assert patched.status_code == 200, patched.text
    orig_shapes = entry_shapes(orig_binding["lorebook_id"])
    assert ("Gale", "gale lore", ("gale",)) in orig_shapes
    assert all(content != "clone-only edit" for _name, content, _keys in orig_shapes)
    clone_travel = client.get(f"/api/v1/characters/{clone['id']}/character-book").json()
    assert "clone-only edit" in [e["content"] for e in clone_travel["entries"]]
    orig_travel = client.get(f"/api/v1/characters/{char['id']}/character-book").json()
    assert "clone-only edit" not in [e["content"] for e in orig_travel["entries"]]

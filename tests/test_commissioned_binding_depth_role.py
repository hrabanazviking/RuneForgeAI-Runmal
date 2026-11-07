"""Commissioned slice (post-P-048 gate): binding depth/role.

Gate finding F2 (P-047 evidence, P-048 gate record):
``binding.normalise_book_entry`` dropped ``depth`` / ``role``, so
embedded character-book entries could not carry P-038 placement
into materialisation. This battery pins the fix end to end:

- ``normalise_book_entry`` carries ``position`` / ``depth`` /
  ``role`` whole, normalised by ``lorebooks.placement`` -- the
  single vocabulary owner (position delegation also closes the
  numeric-string split: the old module-local normaliser mapped
  ``"4"`` to ``before_char`` where placement maps it to
  ``at_depth``);
- a bad depth degrades to ``None`` (undeclared, never an
  invented number) and a bad role degrades to ``system``;
  absent placement yields ``before_char`` / ``None`` /
  ``system`` -- identical stored behaviour to before the fix
  for entries without placement;
- ``materialise_character_book`` stores depth/role on the
  ``LoreEntry`` row and ``serialise_bound_book`` emits them, so
  the full character-book round-trip (normalise -> materialise
  -> serialise -> normalise) is a fixed point;
- the API path (character creation with an embedded book, the
  bound lorebook read, the travelling character-book read, and
  duplication) carries placement whole.

No migration: LoreEntry already carries the depth/role columns
(P-038, migration 0030); head stays 0032.
Entries are authored fresh in this module (P-005 discipline).
No mirror source was consulted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User
from runmal.lorebooks.binding import (
    materialise_character_book,
    normalise_book_entry,
    serialise_bound_book,
)
from runmal.lorebooks.service import entry_to_dict, list_entries


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


def card(name="Sigrun", book=None):
    return {
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
        "character_book": book if book is not None else {"name": "Lore", "entries": []},
    }


def book_entry(name, content, **kw):
    entry = {"name": name, "comment": name, "content": content, "keys": [name.lower()], "constant": True}
    entry.update(kw)
    return entry


# ------------------------------------------------- normalise: placement rides


def test_normalise_at_depth_names_carry_whole():
    out = normalise_book_entry({"position": "at_depth", "depth": 2, "role": "user"})
    assert out["position"] == "at_depth"
    assert out["depth"] == 2
    assert out["role"] == "user"


def test_normalise_worldinfo_codes_carry_whole():
    out = normalise_book_entry({"position": 4, "depth": 3, "role": 2})
    assert out["position"] == "at_depth"
    assert out["depth"] == 3
    assert out["role"] == "assistant"
    out = normalise_book_entry({"position": 4, "depth": 0, "role": 0})
    assert out["depth"] == 0  # depth 0 is declared, not absent
    assert out["role"] == "system"
    out = normalise_book_entry({"position": 1, "role": 1})
    assert out["position"] == "after_char"
    assert out["role"] == "user"


def test_normalise_position_numeric_string_uses_placement_vocabulary():
    # Regression: binding's old module-local normaliser mapped the
    # string "4" to before_char; placement (the single owner) maps
    # it to at_depth, like the file legs do.
    assert normalise_book_entry({"position": "4"})["position"] == "at_depth"
    assert normalise_book_entry({"position": "0"})["position"] == "before_char"
    assert normalise_book_entry({"position": "1"})["position"] == "after_char"


def test_normalise_depth_coercions():
    assert normalise_book_entry({"depth": "2"})["depth"] == 2
    assert normalise_book_entry({"depth": 3.0})["depth"] == 3
    assert normalise_book_entry({"depth": " 5 "})["depth"] == 5


def test_normalise_role_name_case_and_codes():
    assert normalise_book_entry({"role": "User"})["role"] == "user"
    assert normalise_book_entry({"role": "ASSISTANT"})["role"] == "assistant"
    assert normalise_book_entry({"role": "1"})["role"] == "user"


def test_normalise_absent_placement_is_todays_defaults():
    out = normalise_book_entry({"name": "Plain", "content": "lore"})
    assert out["position"] == "before_char"
    assert out["depth"] is None
    assert out["role"] == "system"
    assert "depth" in out and "role" in out  # keys exist even when absent


@pytest.mark.parametrize("bad", [-1, -100, "deep", "", 2.5, True, False, [], {}])
def test_normalise_bad_depth_degrades_to_none(bad):
    out = normalise_book_entry({"position": "at_depth", "depth": bad, "role": "user"})
    assert out["depth"] is None  # undeclared, never clamped or invented
    assert out["position"] == "at_depth"
    assert out["role"] == "user"


@pytest.mark.parametrize("bad", ["admin", "", 99, -1, 1.5, True, [], {}])
def test_normalise_bad_role_degrades_to_system(bad):
    out = normalise_book_entry({"position": "at_depth", "depth": 2, "role": bad})
    assert out["role"] == "system"  # role has no absence sentinel
    assert out["depth"] == 2


def test_normalise_before_after_entries_still_store_companions():
    # Storage keeps declared companions for every entry; only
    # placement_for ignores them for before/after (P-038 rule).
    out = normalise_book_entry({"position": "before_char", "depth": 7, "role": "assistant"})
    assert out["depth"] == 7
    assert out["role"] == "assistant"


# --------------------------------------- materialise -> serialise round-trip


async def _seed_character(factory):
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.flush()
        character = Character(user_id=user.id, name="Sigrun", card_json="{}")
        session.add(character)
        await session.commit()
        return user.id, character.id


ROUND_TRIP_BOOK = {
    "name": "Sigrun Lore",
    "entries": [
        {"name": "Deep", "content": "deep lore", "keys": ["deep"], "position": "at_depth", "depth": 2, "role": "user"},
        {"name": "Coded", "content": "coded lore", "keys": ["coded"], "position": 4, "depth": 0, "role": 2},
        {"name": "Plain", "content": "plain lore", "keys": ["plain"]},
        {"name": "Broken", "content": "broken lore", "keys": ["broken"], "position": "at_depth", "depth": -3, "role": "admin"},
    ],
}

EXPECTED_PLACEMENT = {
    "Deep": ("at_depth", 2, "user"),
    "Coded": ("at_depth", 0, "assistant"),
    "Plain": ("before_char", None, "system"),
    "Broken": ("at_depth", None, "system"),
}


async def test_materialise_stores_placement_and_serialise_emits_it(tmp_path):
    factory = make_factory(tmp_path)
    user_id, character_id = await _seed_character(factory)
    async with factory() as session:
        character = await session.get(Character, character_id)
        binding = await materialise_character_book(session, user_id, character, ROUND_TRIP_BOOK)
        assert binding is not None
        await session.commit()
        rows = await list_entries(session, user_id, binding.lorebook_id)
        stored = {row.name: entry_to_dict(row) for row in rows}
        assert set(stored) == set(EXPECTED_PLACEMENT)
        for name, (position, depth, role) in EXPECTED_PLACEMENT.items():
            assert stored[name]["position"] == position, name
            assert stored[name]["depth"] == depth, name
            assert stored[name]["role"] == role, name
        serialised = await serialise_bound_book(session, binding)
    travelled = {e["name"]: e for e in serialised["entries"]}
    assert set(travelled) == set(EXPECTED_PLACEMENT)
    for name, (position, depth, role) in EXPECTED_PLACEMENT.items():
        assert travelled[name]["position"] == position, name
        assert travelled[name]["depth"] == depth, name
        assert travelled[name]["role"] == role, name
    # The serialised book re-normalises to itself: the round-trip
    # is a fixed point, so export -> re-import loses nothing.
    for entry in serialised["entries"]:
        again = normalise_book_entry(entry)
        expected = EXPECTED_PLACEMENT[entry["name"]]
        assert (again["position"], again["depth"], again["role"]) == expected


def test_migration_head_unchanged():
    assert MIGRATIONS[-1][0] == "0037"  # head moved by P-066 (PROVISIONAL 0037)


# --------------------------------------------------------------------- API


def _create_with_book(client):
    payload = card(book={"name": "Sigrun Lore", "entries": [
        book_entry("Deep", "deep lore", position="at_depth", depth=2, role="user"),
        book_entry("Coded", "coded lore", position=4, depth=0, role=2),
        book_entry("Plain", "plain lore"),
    ]})
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _binding(client, character_id):
    resp = client.get(f"/api/v1/characters/{character_id}/lorebook-binding")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_api_materialised_entries_carry_placement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = _create_with_book(client)
    binding = _binding(client, char["id"])
    assert binding["bound"] is True
    book = client.get(f"/api/v1/lorebooks/{binding['lorebook_id']}")
    assert book.status_code == 200, book.text
    entries = {e["name"]: e for e in book.json()["entries"]}
    assert (entries["Deep"]["position"], entries["Deep"]["depth"], entries["Deep"]["role"]) == ("at_depth", 2, "user")
    assert (entries["Coded"]["position"], entries["Coded"]["depth"], entries["Coded"]["role"]) == ("at_depth", 0, "assistant")
    assert (entries["Plain"]["position"], entries["Plain"]["depth"], entries["Plain"]["role"]) == ("before_char", None, "system")


def test_api_travelling_book_round_trips_placement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = _create_with_book(client)
    travel = client.get(f"/api/v1/characters/{char['id']}/character-book")
    assert travel.status_code == 200, travel.text
    entries = {e["name"]: e for e in travel.json()["entries"]}
    assert (entries["Deep"]["position"], entries["Deep"]["depth"], entries["Deep"]["role"]) == ("at_depth", 2, "user")
    assert (entries["Coded"]["position"], entries["Coded"]["depth"], entries["Coded"]["role"]) == ("at_depth", 0, "assistant")
    assert (entries["Plain"]["position"], entries["Plain"]["depth"], entries["Plain"]["role"]) == ("before_char", None, "system")


def test_api_duplicate_clone_keeps_placement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = _create_with_book(client)
    dup = client.post(f"/api/v1/characters/{char['id']}/duplicate")
    assert dup.status_code == 201, dup.text
    clone_binding = _binding(client, dup.json()["id"])
    assert clone_binding["bound"] is True
    book = client.get(f"/api/v1/lorebooks/{clone_binding['lorebook_id']}")
    assert book.status_code == 200, book.text
    entries = {e["name"]: e for e in book.json()["entries"]}
    assert (entries["Deep"]["position"], entries["Deep"]["depth"], entries["Deep"]["role"]) == ("at_depth", 2, "user")
    assert (entries["Coded"]["position"], entries["Coded"]["depth"], entries["Coded"]["role"]) == ("at_depth", 0, "assistant")

"""P-025 acceptance: duplicate & version handling.

Roadmap line: same-name cards versioned, never silently overwritten.

Contract under test (docs/DUPLICATE_AND_VERSION_HANDLING_2026-11-06.md):
- Migration 0022 adds version_no / lineage_id / content_hash.
- Creating a character whose name already exists for the user either
  matches a live same-name sibling exactly (the sibling is returned
  unchanged, flagged as an exact duplicate; HTTP 200 with
  ``duplicate_exact: true``) or becomes the next version in that
  name's lineage (HTTP 201). Row names stay unsuffixed.
- Identity is the SHA-256 of the export_json v2 stored text (P-022),
  always computed live: an in-place rewrite of ``card_json`` (update /
  editor / organise) is still recognised, because the stored column
  is only a creation-time cache.
- Version numbers are never reused inside a lineage: numbering counts
  soft-deleted rows, while deduplication scans live siblings only.
- GET /characters/{id}/versions lists a lineage;
  GET /characters/{id}/versions/{n} returns one version plus its card.
- ``duplicate_character`` (copy) is unchanged: a separate ``(copy)``
  lineage root.
- The P-022 bulk-import exact-duplicate refusal is untouched, and a
  bulk-imported changed same-name card lands as a new version with a
  ``versioned:v<n>`` note.

Fixtures are authored fresh here; helper patterns mirror
test_s106_characters.py and test_p022_bulk_library_import.py.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.cards import import_card
from runmal.cards.exporter import export_json
from runmal.characters import versioning
from runmal.characters.service import (
    create_character,
    create_character_from_card,
    list_characters,
    update_character,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User
from runmal.library.service import import_library_uploads

# ---------------------------------------------------------------- helpers


def card_dict(name="Asta", **over):
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "First description.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": "forge",
        "extensions": {},
    }
    card.update(over)
    return card


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
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


def post_card(client, card, name=None, expect=None):
    body = {"card": card}
    if name is not None:
        body["name"] = name
    resp = client.post("/api/v1/characters", json=body)
    if expect is not None:
        assert resp.status_code == expect, resp.text
    return resp


# ---------------------------------------------------------------- migration


def test_migration_head_is_0028_p036() -> None:
    assert MIGRATIONS[-1][0] == "0031"


def test_migration_0022_columns_and_indexes(tmp_path) -> None:
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0031"
    conn = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(characters)")
        }
        assert {"version_no", "lineage_id", "content_hash"} <= columns
        index_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "ix_characters_user_lineage" in index_names
        assert "ix_characters_user_name" in index_names
    finally:
        conn.close()


# ---------------------------------------------------------------- HTTP create


def test_first_create_is_v1_lineage_root(app_client) -> None:
    created = post_card(app_client, card_dict(), expect=201).json()
    assert created["name"] == "Asta"
    assert created["version_no"] == 1
    assert created["lineage_id"] == created["id"]
    assert len(created["content_hash"]) == 64


def test_exact_duplicate_returns_existing_no_new_row(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    again = post_card(app_client, card_dict(), expect=200)
    payload = again.json()
    assert payload["duplicate_exact"] is True
    assert payload["id"] == first["id"]
    assert payload["version_no"] == 1
    listed = app_client.get("/api/v1/characters").json()
    assert [c["id"] for c in listed] == [first["id"]]


def test_changed_same_name_becomes_v2_unsuffixed(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    second = post_card(
        app_client,
        card_dict(description="Second description."),
        expect=201,
    ).json()
    assert second["id"] != first["id"]
    assert second["name"] == "Asta"
    assert second["version_no"] == 2
    assert second["lineage_id"] == first["lineage_id"]
    assert second["content_hash"] != first["content_hash"]
    listed = app_client.get("/api/v1/characters").json()
    assert len(listed) == 2


def test_versions_increase_monotonically(app_client) -> None:
    seen = []
    for desc in ("One.", "Two.", "Three."):
        created = post_card(
            app_client, card_dict(description=desc), expect=201
        ).json()
        seen.append(created)
    assert [c["version_no"] for c in seen] == [1, 2, 3]
    assert len({c["lineage_id"] for c in seen}) == 1
    assert len({c["id"] for c in seen}) == 3


def test_same_content_different_name_is_separate_lineage(app_client) -> None:
    card = card_dict()
    first = post_card(app_client, card, name="Asta", expect=201).json()
    other = post_card(app_client, card, name="Brunhild", expect=201).json()
    assert other["name"] == "Brunhild"
    assert other["version_no"] == 1
    assert other["lineage_id"] == other["id"]
    assert other["lineage_id"] != first["lineage_id"]


# ---------------------------------------------------------------- HTTP versions


def test_versions_list_and_detail(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    second = post_card(
        app_client,
        card_dict(description="Second description."),
        expect=201,
    ).json()

    listing = app_client.get(
        f"/api/v1/characters/{first['id']}/versions"
    ).json()
    assert listing["lineage_id"] == first["lineage_id"]
    assert listing["latest_version_no"] == 2
    assert [v["version_no"] for v in listing["versions"]] == [1, 2]
    assert [v["is_latest"] for v in listing["versions"]] == [False, True]
    assert listing["versions"][0]["character_id"] == first["id"]
    assert listing["versions"][1]["character_id"] == second["id"]

    # The same lineage is reachable from any of its versions.
    via_second = app_client.get(
        f"/api/v1/characters/{second['id']}/versions"
    ).json()
    assert via_second["lineage_id"] == listing["lineage_id"]
    assert [v["version_no"] for v in via_second["versions"]] == [1, 2]

    detail = app_client.get(
        f"/api/v1/characters/{first['id']}/versions/1"
    ).json()
    assert detail["version_no"] == 1
    assert detail["content_hash"] == listing["versions"][0]["content_hash"]
    assert "First description." in json.dumps(detail["card"])


def test_version_not_found_wording(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    resp = app_client.get(f"/api/v1/characters/{first['id']}/versions/99")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "version not found"


def test_versions_missing_character_wording(app_client) -> None:
    resp = app_client.get("/api/v1/characters/missing/versions")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "character not found"
    resp = app_client.get("/api/v1/characters/missing/versions/1")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "character not found"


def test_original_version_never_silently_overwritten(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    post_card(
        app_client,
        card_dict(description="Second description."),
        expect=201,
    )
    fetched = app_client.get(f"/api/v1/characters/{first['id']}").json()
    assert fetched["version_no"] == 1
    detail = app_client.get(
        f"/api/v1/characters/{first['id']}/versions/1"
    ).json()
    assert "First description." in json.dumps(detail["card"])
    assert "Second description." not in json.dumps(detail["card"])


# ---------------------------------------------------------------- HTTP delete interplay


def test_version_number_not_reused_after_delete(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    second = post_card(
        app_client,
        card_dict(description="Second description."),
        expect=201,
    ).json()
    assert app_client.delete(
        f"/api/v1/characters/{second['id']}"
    ).status_code == 200
    third = post_card(
        app_client,
        card_dict(description="Third description."),
        expect=201,
    ).json()
    assert third["version_no"] == 3
    assert third["lineage_id"] == first["lineage_id"]
    listing = app_client.get(
        f"/api/v1/characters/{first['id']}/versions"
    ).json()
    assert [v["version_no"] for v in listing["versions"]] == [1, 2, 3]
    by_no = {v["version_no"]: v for v in listing["versions"]}
    assert by_no[2]["deleted"] is True
    assert by_no[3]["deleted"] is False
    assert listing["latest_version_no"] == 3


def test_reimport_after_delete_is_fresh_create(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    assert app_client.delete(
        f"/api/v1/characters/{first['id']}"
    ).status_code == 200
    again = post_card(app_client, card_dict(), expect=201).json()
    assert again["id"] != first["id"]
    assert again["version_no"] == 1
    assert "duplicate_exact" not in again


def test_copy_is_separate_lineage_root(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    copy = app_client.post(
        f"/api/v1/characters/{first['id']}/duplicate"
    ).json()
    assert copy["name"] == "Asta (copy)"
    assert copy["version_no"] == 1
    assert copy["lineage_id"] == copy["id"]
    assert copy["lineage_id"] != first["lineage_id"]


# ---------------------------------------------------------------- service level


async def test_service_exact_duplicate_flag_and_single_row(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        first = await create_character(session, user_id, card_dict())
        first_id = first.id
    async with factory() as session:
        again = await create_character(session, user_id, card_dict())
        assert again.id == first_id
        assert getattr(again, versioning.DUPLICATE_ATTR, False) is True
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert [c.id for c in rows] == [first_id]


async def test_live_hash_recognises_inplace_update(tmp_path) -> None:
    """update_character rewrites card_json without touching the
    content_hash column; dedup must still hit, because identity is
    always computed live from the stored text."""
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        created = await create_character(session, user_id, card_dict())
        char_id = created.id
    async with factory() as session:
        updated = await update_character(
            session,
            user_id,
            char_id,
            card_data=card_dict(description="Second description."),
        )
        assert updated is not None
    async with factory() as session:
        again = await create_character(
            session,
            user_id,
            card_dict(description="Second description."),
        )
        assert again.id == char_id
        assert getattr(again, versioning.DUPLICATE_ATTR, False) is True
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert [c.id for c in rows] == [char_id]


async def test_hash_identity_matches_p022_digest(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card(json.dumps(card_dict()).encode(), "card.json")
    stored_text = export_json(card, "2").decode("utf-8")
    expected = hashlib.sha256(stored_text.encode("utf-8")).hexdigest()
    assert versioning.content_hash_of(stored_text) == expected
    async with factory() as session:
        character = await create_character_from_card(session, user_id, card)
        assert character.content_hash == expected
        assert versioning.effective_content_hash(character) == expected


async def test_legacy_row_is_own_lineage_and_joins(tmp_path) -> None:
    """A pre-P-025 row (lineage_id NULL) is its own lineage root, and
    new same-name content joins that lineage as the next version."""
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card(json.dumps(card_dict()).encode(), "card.json")
    stored_text = export_json(card, "2").decode("utf-8")
    async with factory() as session:
        legacy = Character(
            user_id=user_id, name="Asta", card_json=stored_text
        )
        session.add(legacy)
        await session.commit()
        legacy_id = legacy.id
    async with factory() as session:
        listing = await versioning.list_versions(session, user_id, legacy_id)
        assert listing is not None
        assert listing["lineage_id"] == legacy_id
        assert [v["version_no"] for v in listing["versions"]] == [1]
        assert listing["versions"][0]["content_hash"] == (
            hashlib.sha256(stored_text.encode("utf-8")).hexdigest()
        )
    async with factory() as session:
        created = await create_character(
            session,
            user_id,
            card_dict(description="Second description."),
        )
        assert created.version_no == 2
        assert created.lineage_id == legacy_id


# ---------------------------------------------------------------- bulk import interplay


async def test_bulk_import_versions_changed_same_name(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    first_bytes = json.dumps(card_dict()).encode()
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("asta.json", first_bytes)]
        )
        assert [e.outcome for e in report.entries] == ["accepted"]
    changed_bytes = json.dumps(
        card_dict(description="Second description.")
    ).encode()
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("asta-v2.json", changed_bytes)]
        )
        entry = report.entries[0]
        assert entry.outcome == "accepted"
        assert "versioned:v2" in entry.notes
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert len(rows) == 2
    # The P-022 exact-duplicate refusal is untouched.
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("asta-again.json", first_bytes)]
        )
        entry = report.entries[0]
        assert entry.outcome == "refused"
        assert str(entry.reason_code) == "duplicate_exact"
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert len(rows) == 2

"""P-073 acceptance: chat metadata — titles, tags, summaries
auto-generated and editable; the library view at scale.

Contract under test:
- Migration head is PROVISIONAL 0039: chats.summary +
  chats.metadata_json columns, chat_tags + chat_organisation
  tables.
- Generation (runmal.chats.metadata, generator extractive-v1)
  is deterministic and extractive: title from the first user
  message, summary from opening + most-salient later sentence,
  tags from content-word frequency. No model is involved.
- Metadata is editable per field; manual fields are marked
  manual and regeneration skips them unless forced; the
  regenerate result reports generated + skipped.
- The library view paginates, filters (q / tags any+all /
  favourites / character), and sorts in SQL; /chats/tags counts.
- Owner scope everywhere: another user's chat is invisible.
Fixtures mirror test_p070_group_deepening.py.
"""

import asyncio
import copy
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import metadata as meta
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())

DRAGON_MESSAGES = [
    ("user", "Tell me about the dragons of the northern fjords and their ancient hoards."),
    (
        "assistant",
        "The dragons guard hoards of gold beneath the fjords. "
        "Sailors fear the dragons of the north.",
    ),
    ("user", "Do the dragons still guard those hoards today?"),
]


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0041"  # P-073 PROVISIONAL migration
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_chat(client, character_id=None, title=""):
    body = {"title": title}
    if character_id:
        body["character_id"] = character_id
    created = client.post("/api/v1/chats", json=body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def post_message(client, chat_id, role, content):
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": role, "content": content}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def dragon_chat(client):
    cid = make_character(client, "Smaug Scholar")
    chat_id = make_chat(client, cid)
    for role, content in DRAGON_MESSAGES:
        post_message(client, chat_id, role, content)
    return chat_id


# -- Migration -------------------------------------------------------------


def test_migration_0039_shape(tmp_path):
    db_path = tmp_path / "mig.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0041"
    conn = sqlite3.connect(db_path)
    try:
        chat_cols = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
        assert {"summary", "metadata_json"} <= chat_cols
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"chat_tags", "chat_organisation"} <= tables
    finally:
        conn.close()


# -- Pure generation ---------------------------------------------------------


def _msgs(pairs):
    return [{"role": role, "content": content} for role, content in pairs]


def test_generate_title_from_first_user_message():
    title = meta.generate_title(_msgs(DRAGON_MESSAGES), "Smaug Scholar")
    assert title.startswith("Tell me about the dragons")
    assert title.endswith("…")
    assert len(title) <= meta.TITLE_AUTO_MAX


def test_generate_title_fallbacks():
    assert meta.generate_title([], "Astrid") == "Chat with Astrid"
    assert meta.generate_title([], None) == "Untitled chat"
    assert meta.generate_title(_msgs([("assistant", "Hail, traveller.")])) == "Hail, traveller."


def test_generate_summary_extractive():
    summary = meta.generate_summary(_msgs(DRAGON_MESSAGES))
    assert summary.startswith("Tell me about the dragons")
    assert "guard hoards of gold beneath the fjords" in summary
    assert len(summary) <= meta.SUMMARY_AUTO_MAX


def test_generate_summary_empty_chat():
    assert meta.generate_summary([]) == ""
    assert meta.generate_summary(_msgs([("user", "   ")])) == ""


def test_generate_tags_frequency_ranked():
    tags = meta.generate_tags(_msgs(DRAGON_MESSAGES))
    assert tags[0] == "dragons"
    assert {"fjords", "guard", "hoards"} <= set(tags)
    assert "tell" not in tags and "about" not in tags


def test_generate_tags_needs_two_candidates():
    assert meta.generate_tags(_msgs([("user", "dragons dragons dragons")])) == []
    assert meta.generate_tags([]) == []


def test_generation_is_deterministic():
    msgs = _msgs(DRAGON_MESSAGES)
    assert meta.generate_title(msgs) == meta.generate_title(msgs)
    assert meta.generate_summary(msgs) == meta.generate_summary(msgs)
    assert meta.generate_tags(msgs) == meta.generate_tags(msgs)


def test_validation_limits():
    with pytest.raises(ValueError):
        meta.validate_title("x" * (meta.MAX_TITLE_LEN + 1))
    with pytest.raises(ValueError):
        meta.validate_title("   ")
    with pytest.raises(ValueError):
        meta.validate_summary("x" * (meta.MAX_SUMMARY_LEN + 1))
    with pytest.raises(ValueError):
        meta.normalise_chat_tags("not-a-list")
    pairs = meta.normalise_chat_tags(["Sci Fi", "sci  fi", "Quest"])
    assert pairs == [("Sci Fi", "sci fi"), ("Quest", "quest")]


# -- HTTP: metadata lifecycle -------------------------------------------------


def test_metadata_defaults_then_regenerate(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = dragon_chat(client)
    got = client.get(f"/api/v1/chats/{chat_id}/metadata")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["summary"] == "" and body["tags"] == []
    assert body["is_favourite"] is False
    assert body["message_count"] == 3
    assert body["metadata"]["title_source"] == "unset"
    assert body["metadata"]["generator"] is None

    regen = client.post(f"/api/v1/chats/{chat_id}/metadata/regenerate", json={})
    assert regen.status_code == 200, regen.text
    body = regen.json()
    assert body["generated"] == ["title", "summary", "tags"]
    assert body["skipped"] == []
    assert body["title"].startswith("Tell me about the dragons")
    assert "guard hoards of gold" in body["summary"]
    # Read-back order is tag_key order (the P-024 presentation);
    # the frequency ranking decides WHICH tags are chosen and is
    # asserted at the pure-function level above.
    assert body["tags"] == ["ancient", "dragons", "fjords", "guard", "hoards"]
    prov = body["metadata"]
    assert prov["title_source"] == prov["summary_source"] == prov["tags_source"] == "auto"
    assert prov["generator"] == "extractive-v1"
    assert prov["generated_from"] == 3
    assert prov["generated_at"]

    chat = client.get(f"/api/v1/chats/{chat_id}").json()
    assert chat["title"] == body["title"]
    assert chat["summary"] == body["summary"]
    assert chat["metadata"]["generator"] == "extractive-v1"

    kinds = [e["kind"] for e in client.get(f"/api/v1/chats/{chat_id}/events").json()]
    assert "chat.metadata_generated" in kinds


def test_manual_edit_survives_regenerate_unless_forced(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = dragon_chat(client)
    client.post(f"/api/v1/chats/{chat_id}/metadata/regenerate", json={})
    edited = client.put(
        f"/api/v1/chats/{chat_id}/metadata",
        json={"title": "My Dragon Notes", "tags": ["Lore", "Dragons"]},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["title"] == "My Dragon Notes"
    assert body["tags"] == ["Dragons", "Lore"]
    assert body["metadata"]["title_source"] == "manual"
    assert body["metadata"]["tags_source"] == "manual"
    assert body["metadata"]["summary_source"] == "auto"

    regen = client.post(f"/api/v1/chats/{chat_id}/metadata/regenerate", json={})
    body = regen.json()
    assert set(body["skipped"]) == {"title", "tags"}
    assert body["generated"] == ["summary"]
    assert body["title"] == "My Dragon Notes"
    assert body["tags"] == ["Dragons", "Lore"]

    forced = client.post(
        f"/api/v1/chats/{chat_id}/metadata/regenerate",
        json={"fields": ["title"], "force": True},
    )
    body = forced.json()
    assert body["generated"] == ["title"] and body["skipped"] == []
    assert body["title"].startswith("Tell me about the dragons")
    assert body["metadata"]["title_source"] == "auto"


def test_metadata_validation_and_404s(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = dragon_chat(client)
    bad_title = client.put(
        f"/api/v1/chats/{chat_id}/metadata", json={"title": "x" * 201}
    )
    assert bad_title.status_code == 422
    bad_tags = client.put(
        f"/api/v1/chats/{chat_id}/metadata", json={"tags": "quest"}
    )
    assert bad_tags.status_code == 422
    bad_field = client.post(
        f"/api/v1/chats/{chat_id}/metadata/regenerate", json={"fields": ["nope"]}
    )
    assert bad_field.status_code == 422
    assert client.get("/api/v1/chats/nope/metadata").status_code == 404
    assert client.put("/api/v1/chats/nope/metadata", json={"title": "x"}).status_code == 404
    assert client.post("/api/v1/chats/nope/metadata/regenerate", json={}).status_code == 404
    resp = client.put(
        "/api/v1/chats/nope/favourite", json={"is_favourite": True}
    )
    assert resp.status_code == 404


def test_regenerate_empty_chat(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    regen = client.post(f"/api/v1/chats/{chat_id}/metadata/regenerate", json={})
    body = regen.json()
    assert body["title"] == "Untitled chat"
    assert body["summary"] == ""
    assert body["tags"] == []
    assert body["metadata"]["generated_from"] == 0


# -- HTTP: the library view at scale -------------------------------------------


def _library_chat(client, title, tags=None, summary=None, favourite=False):
    chat_id = make_chat(client, title=title)
    updates = {}
    if tags is not None:
        updates["tags"] = tags
    if summary is not None:
        updates["summary"] = summary
    if updates:
        resp = client.put(f"/api/v1/chats/{chat_id}/metadata", json=updates)
        assert resp.status_code == 200, resp.text
    if favourite:
        resp = client.put(
            f"/api/v1/chats/{chat_id}/favourite", json={"is_favourite": True}
        )
        assert resp.status_code == 200, resp.text
    return chat_id


def test_library_pagination_and_sort(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _library_chat(client, "Beta Tales")
    _library_chat(client, "Alpha Tales")
    _library_chat(client, "Gamma Tales")
    page = client.get("/api/v1/chats/library", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    rest = client.get("/api/v1/chats/library", params={"limit": 2, "offset": 2}).json()
    assert rest["total"] == 3 and len(rest["items"]) == 1
    by_title = client.get("/api/v1/chats/library", params={"sort": "title"}).json()
    assert [i["title"] for i in by_title["items"]] == [
        "Alpha Tales",
        "Beta Tales",
        "Gamma Tales",
    ]
    clamped = client.get("/api/v1/chats/library", params={"limit": 5000}).json()
    assert clamped["total"] == 3 and len(clamped["items"]) == 3


def test_library_filters(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _library_chat(client, "Dragon Hoard", tags=["dragons", "gold"], summary="A shiny hoard.")
    _library_chat(client, "Sea Voyage", tags=["dragons", "sailing"], favourite=True)
    _library_chat(client, "Quiet Garden", tags=["herbs"], summary="Calm and green.")

    by_q = client.get("/api/v1/chats/library", params={"q": "shiny"}).json()
    assert by_q["total"] == 1 and by_q["items"][0]["title"] == "Dragon Hoard"
    by_tag_q = client.get("/api/v1/chats/library", params={"q": "sailing"}).json()
    assert by_tag_q["total"] == 1 and by_tag_q["items"][0]["title"] == "Sea Voyage"
    any_tags = client.get(
        "/api/v1/chats/library", params={"tags": ["gold", "herbs"]}
    ).json()
    assert any_tags["total"] == 2
    all_tags = client.get(
        "/api/v1/chats/library",
        params={"tags": ["dragons", "gold"], "tag_mode": "all"},
    ).json()
    assert all_tags["total"] == 1 and all_tags["items"][0]["title"] == "Dragon Hoard"
    favs = client.get(
        "/api/v1/chats/library", params={"favourites_only": True}
    ).json()
    assert favs["total"] == 1 and favs["items"][0]["is_favourite"] is True
    fav_first = client.get(
        "/api/v1/chats/library", params={"sort": "favourites_first"}
    ).json()
    assert fav_first["items"][0]["title"] == "Sea Voyage"

    tags = client.get("/api/v1/chats/tags").json()
    counts = {row["tag_key"]: row["count"] for row in tags}
    assert counts == {"dragons": 2, "gold": 1, "sailing": 1, "herbs": 1}
    assert tags[0]["tag_key"] == "dragons"


def test_library_route_not_swallowed_by_chat_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _library_chat(client, "Only Chat")
    resp = client.get("/api/v1/chats/library")
    assert resp.status_code == 200 and resp.json()["total"] == 1


# -- Service: owner scope -------------------------------------------------------


def test_service_owner_scope(tmp_path):
    factory = make_factory(tmp_path)

    async def run():
        async with factory() as session:
            owner = User(name="owner")
            other = User(name="other")
            session.add_all([owner, other])
            await session.commit()
            from runmal.chats.service import create_chat

            chat = await create_chat(session, owner.id, "Secret")
            assert await meta.get_metadata(session, other.id, chat.id) is None
            assert await meta.update_metadata(session, other.id, chat.id, {"title": "x"}) is None
            assert await meta.regenerate_metadata(session, other.id, chat.id) is None
            assert await meta.set_favourite(session, other.id, chat.id, True) is None
            library = await meta.list_chat_library(session, other.id)
            assert library["total"] == 0
            mine = await meta.get_metadata(session, owner.id, chat.id)
            assert mine is not None and mine["title"] == "Secret"

    asyncio.run(run())

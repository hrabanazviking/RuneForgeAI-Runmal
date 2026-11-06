"""P-040 acceptance: global + persona + chat lore scopes.

Roadmap line: *Global + persona + chat lore scopes, layered like
the mirrors' (world -> character -> chat) with per-scope budgets.*

Contract under test:
- ``runmal.lorebooks.scopes`` pure layer: ``SCOPE_KINDS`` is
  {global, character, persona, chat} and ``LAYER_ORDER`` is
  (global, character, persona, chat); ``check_scope_kind`` is
  strict, ``normalise_scope_kind`` maps None to global and is
  otherwise tolerant; ``normalise_scope_budget`` keeps None
  (unlimited) and 0 (muted) and positive ints, and refuses
  bools / negatives / non-ints; ``check_scope_owner`` refuses an
  owner on global and an empty owner elsewhere.
- ``resolve_layers`` is deterministic: layers come back in
  LAYER_ORDER, books inside a layer sort by (position, book id),
  a book assigned into several layers survives ONLY in the most
  specific one with the losers reported in ``shadowed``, and a
  book twice in one layer collapses to one assignment.
- DB: migration 0032 creates ``lorebook_scopes`` with the
  unique (lorebook, kind, owner) triple; ``MIGRATIONS[-1][0]``
  is "0032" and re-running migrations applies nothing twice.
- Service: assign upserts on the triple; unowned book /
  character / chat targets are indistinguishable from missing
  ones (ValueError "... not found"); unassign reports whether
  a row existed; listing is ownership-scoped.
- Layered preview: layers compose in declared order, each with
  its OWN budget (a layer's enforced budget is the minimum of
  its assignments' declared budgets); an over-budget layer
  discards with reason ``scope_over_budget`` and never starves
  another layer; budget 0 mutes only its layer; the P-039
  binding contributes its book to the character layer with
  ``via == "binding"``; every layer reports books / budget /
  tokens / included / discarded and every row is tagged with
  its scope, so the composed result is inspectable per scope.
- API: PUT/DELETE /lorebooks/{id}/scope, GET
  /lorebooks/{id}/scopes, GET /lore-scopes, POST
  /chats/{id}/lore-preview, and prompt-inspect with ``chat_id``
  wires the scoped layers in with ``lorebook:<name>@<scope>``
  provenance and a ``lore_scopes`` summary; without ``chat_id``
  the trace has no ``lore_scopes`` key (pre-P-040 behaviour).
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, Chat, Lorebook, User
from runmal.lorebooks import scopes
from runmal.lorebooks.scopes import (
    LAYER_ORDER,
    SCOPE_KINDS,
    ScopedBook,
    check_scope_kind,
    check_scope_owner,
    normalise_scope_budget,
    normalise_scope_kind,
    resolve_layers,
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


async def make_character(factory, user_id, name="Sigrun") -> str:
    async with factory() as session:
        character = Character(user_id=user_id, name=name)
        session.add(character)
        await session.commit()
        return character.id


async def make_chat(factory, user_id, character_id=None, title="Hall") -> str:
    async with factory() as session:
        chat = Chat(user_id=user_id, title=title, character_id=character_id)
        session.add(chat)
        await session.commit()
        return chat.id


async def make_book(factory, user_id, name="World") -> str:
    async with factory() as session:
        book = Lorebook(user_id=user_id, name=name)
        session.add(book)
        await session.commit()
        return book.id


def api_character(client, name="Sigrun"):
    payload = {
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
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def api_book(client, name="World", entries=()):
    resp = client.post("/api/v1/lorebooks", json={"name": name})
    assert resp.status_code == 201, resp.text
    book = resp.json()
    for entry in entries:
        resp = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json=entry)
        assert resp.status_code == 201, resp.text
    return book


def const_entry(name, content, **kw):
    entry = {"name": name, "content": content, "keys": [name.lower()], "constant": True}
    entry.update(kw)
    return entry


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- pure vocab


def test_scope_kinds_and_layer_order():
    assert SCOPE_KINDS == {"global", "character", "persona", "chat"}
    assert LAYER_ORDER == ("global", "character", "persona", "chat")


def test_check_scope_kind_strict():
    for kind in ("global", "character", "persona", "chat"):
        assert check_scope_kind(kind) == kind
    for bad in ("Global", " global", "world", "", None, 3):
        with pytest.raises(ValueError):
            check_scope_kind(bad)


def test_normalise_scope_kind_tolerant():
    assert normalise_scope_kind(None) == "global"
    assert normalise_scope_kind(" Chat ") == "chat"
    assert normalise_scope_kind("PERSONA") == "persona"
    with pytest.raises(ValueError):
        normalise_scope_kind("world")
    with pytest.raises(ValueError):
        normalise_scope_kind(7)


def test_normalise_scope_budget():
    assert normalise_scope_budget(None) is None
    assert normalise_scope_budget(0) == 0
    assert normalise_scope_budget(250) == 250
    for bad in (-1, True, False, 1.5, "10"):
        with pytest.raises(ValueError):
            normalise_scope_budget(bad)


def test_check_scope_owner():
    assert check_scope_owner("global", None) == ""
    assert check_scope_owner("global", "") == ""
    with pytest.raises(ValueError):
        check_scope_owner("global", "chat-1")
    assert check_scope_owner("chat", "chat-1") == "chat-1"
    assert check_scope_owner("persona", "char-1") == "char-1"
    for kind in ("character", "persona", "chat"):
        with pytest.raises(ValueError):
            check_scope_owner(kind, "")
        with pytest.raises(ValueError):
            check_scope_owner(kind, None)


# ------------------------------------------------------------ resolve_layers


def book(book_id, kind, owner="", budget=None, position=0, via="scope"):
    return ScopedBook(
        book_id=book_id, scope_kind=kind, owner_id=owner,
        budget=budget, position=position, via=via,
    )


def test_resolve_layers_empty():
    resolved = resolve_layers([])
    assert resolved.shadowed == ()
    assert all(resolved.layers[kind] == () for kind in LAYER_ORDER)


def test_resolve_layers_groups_by_layer_in_order():
    resolved = resolve_layers([
        book("b-chat", "chat", "c1"),
        book("b-global", "global"),
        book("b-persona", "persona", "p1"),
        book("b-char", "character", "p1"),
    ])
    assert [b.book_id for b in resolved.layers["global"]] == ["b-global"]
    assert [b.book_id for b in resolved.layers["character"]] == ["b-char"]
    assert [b.book_id for b in resolved.layers["persona"]] == ["b-persona"]
    assert [b.book_id for b in resolved.layers["chat"]] == ["b-chat"]
    assert resolved.shadowed == ()


def test_resolve_layers_within_layer_order_position_then_id():
    resolved = resolve_layers([
        book("b2", "global", position=1),
        book("b1", "global", position=1),
        book("b0", "global", position=-1),
    ])
    assert [b.book_id for b in resolved.layers["global"]] == ["b0", "b1", "b2"]


def test_resolve_layers_dedupe_most_specific_wins():
    resolved = resolve_layers([
        book("shared", "global"),
        book("shared", "chat", "c1"),
        book("other", "global"),
    ])
    assert [b.book_id for b in resolved.layers["global"]] == ["other"]
    assert [b.book_id for b in resolved.layers["chat"]] == ["shared"]
    assert list(resolved.shadowed) == [
        {"book_id": "shared", "kept_scope": "chat", "dropped_scope": "global"}
    ]


def test_resolve_layers_dedupe_persona_beats_character_beats_global():
    resolved = resolve_layers([
        book("x", "global"),
        book("x", "character", "p1"),
        book("x", "persona", "p1"),
    ])
    assert [b.book_id for b in resolved.layers["persona"]] == ["x"]
    assert resolved.layers["global"] == ()
    assert resolved.layers["character"] == ()
    dropped = {(s["kept_scope"], s["dropped_scope"]) for s in resolved.shadowed}
    assert dropped == {("persona", "global"), ("persona", "character")}


def test_resolve_layers_same_layer_duplicate_collapses():
    resolved = resolve_layers([
        book("x", "chat", "c1", position=2),
        book("x", "chat", "c1", position=1),
    ])
    assert len(resolved.layers["chat"]) == 1
    assert resolved.layers["chat"][0].position == 1
    assert resolved.shadowed == ()


def test_resolve_layers_deterministic():
    items = [book("b", "chat", "c"), book("a", "global"), book("b", "global")]
    assert resolve_layers(items) == resolve_layers(list(reversed(items)))


def test_resolve_layers_rejects_bad_kind_and_budget():
    with pytest.raises(ValueError):
        resolve_layers([book("x", "world")])
    with pytest.raises(ValueError):
        resolve_layers([book("x", "global", budget=-2)])


# ----------------------------------------------------------------- migration


def test_migration_head_is_0032():
    assert MIGRATIONS[-1][0] == "0032"


def test_migration_creates_table_with_unique_triple(tmp_path):
    db_path = tmp_path / "t.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0032"
    assert current_revision(db_path) == "0032"
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(lorebook_scopes)")}
    assert {
        "id", "user_id", "lorebook_id", "scope_kind", "owner_id",
        "token_budget", "position", "created_at", "updated_at",
    } <= cols
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(lorebook_scopes)")}
    assert "uq_lorebook_scopes_triple" in indexes
    conn.close()
    assert migrate_to_head(db_path) == []


# ------------------------------------------------------------------- service


def test_assign_and_list_global_scope(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        bid = await make_book(factory, uid)
        async with factory() as session:
            scope = await scopes.assign_scope(session, uid, bid, "global")
            assert scope.scope_kind == "global"
            assert scope.owner_id == ""
            assert scope.token_budget is None
            rows = await scopes.list_book_scopes(session, uid, bid)
            assert rows is not None and len(rows) == 1
            layer = await scopes.list_scopes(session, uid, "global")
            assert [row.lorebook_id for row in layer] == [bid]

    run(main())


def test_assign_upsert_updates_budget_and_position(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        bid = await make_book(factory, uid)
        async with factory() as session:
            first = await scopes.assign_scope(
                session, uid, bid, "global", token_budget=100, position=1
            )
            second = await scopes.assign_scope(
                session, uid, bid, "global", token_budget=25, position=3
            )
            assert second.id == first.id
            assert second.token_budget == 25
            assert second.position == 3
            rows = await scopes.list_book_scopes(session, uid, bid)
            assert len(rows) == 1

    run(main())


def test_assign_rejects_unowned_targets(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        other = await make_user(factory, "other")
        bid = await make_book(factory, uid)
        char_id = await make_character(factory, uid)
        chat_id = await make_chat(factory, uid, char_id)
        async with factory() as session:
            with pytest.raises(ValueError, match="lorebook not found"):
                await scopes.assign_scope(session, other, bid, "global")
            with pytest.raises(ValueError, match="character not found"):
                await scopes.assign_scope(
                    session, uid, bid, "persona", owner_id="missing"
                )
            with pytest.raises(ValueError, match="chat not found"):
                await scopes.assign_scope(
                    session, uid, bid, "chat", owner_id="missing"
                )
            ok = await scopes.assign_scope(
                session, uid, bid, "chat", owner_id=chat_id
            )
            assert ok.owner_id == chat_id

    run(main())


def test_assign_validation_errors(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        bid = await make_book(factory, uid)
        async with factory() as session:
            with pytest.raises(ValueError):
                await scopes.assign_scope(session, uid, bid, "world")
            with pytest.raises(ValueError):
                await scopes.assign_scope(
                    session, uid, bid, "global", owner_id="chat-1"
                )
            with pytest.raises(ValueError):
                await scopes.assign_scope(session, uid, bid, "chat")
            with pytest.raises(ValueError):
                await scopes.assign_scope(
                    session, uid, bid, "global", token_budget=-1
                )

    run(main())


def test_unassign_scope(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        bid = await make_book(factory, uid)
        async with factory() as session:
            await scopes.assign_scope(session, uid, bid, "global")
            assert await scopes.unassign_scope(session, uid, bid, "global") is True
            assert await scopes.unassign_scope(session, uid, bid, "global") is False
            rows = await scopes.list_book_scopes(session, uid, bid)
            assert rows == []
            book = await scopes._get_owned_book(session, uid, bid)
            assert book is not None  # the lorebook itself survives

    run(main())


def test_list_book_scopes_unowned_book_is_none(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        other = await make_user(factory, "other")
        bid = await make_book(factory, uid)
        async with factory() as session:
            assert await scopes.list_book_scopes(session, other, bid) is None

    run(main())


# ------------------------------------------------------------ layered preview


async def _seed_layered(factory, uid):
    """One constant-entry book per layer for one chat + character."""
    char_id = await make_character(factory, uid, "Sigrun")
    chat_id = await make_chat(factory, uid, char_id)
    books = {}
    async with factory() as session:
        from runmal.db.models import LoreEntry

        for kind, owner in (
            ("global", None),
            ("character", char_id),
            ("persona", char_id),
            ("chat", chat_id),
        ):
            bid = await make_book(factory, uid, f"{kind}-book")
            async with factory() as inner:
                inner.add(
                    LoreEntry(
                        lorebook_id=bid, user_id=uid, name=f"{kind} fact",
                        content=f"{kind} lore content here", keys_json='["fact"]',
                        secondary_keys_json="[]", constant=True,
                    )
                )
                await inner.commit()
            await scopes.assign_scope(session, uid, bid, kind, owner_id=owner)
            books[kind] = bid
    return char_id, chat_id, books


def test_layered_preview_empty_context(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        async with factory() as session:
            result = await scopes.layered_preview(session, uid, messages=["hi"])
            assert result["layered"] is True
            assert result["layer_order"] == list(LAYER_ORDER)
            assert result["scopes"] == []
            assert result["tokens_used"] == 0

    run(main())


def test_layered_preview_all_four_layers_in_order(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id, chat_id, books = await _seed_layered(factory, uid)
        async with factory() as session:
            result = await scopes.layered_preview(
                session, uid, chat_id=chat_id, messages=["fact"]
            )
            assert [s["scope"] for s in result["scopes"]] == list(LAYER_ORDER)
            for summary in result["scopes"]:
                assert summary["included"] == 1
                assert summary["budget"] is None
                assert summary["tokens_used"] > 0
                assert summary["books"][0]["lorebook_id"] == books[summary["scope"]]
            assert result["tokens_used"] == sum(
                s["tokens_used"] for s in result["scopes"]
            )
            row = result["layers"]["chat"]["entries"][0]
            assert row["scope"] == "chat"
            assert row["lorebook_id"] == books["chat"]
            assert row["scope_via"] == "scope"

    run(main())


def test_layered_preview_chat_book_only_in_its_chat(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id, chat_id, books = await _seed_layered(factory, uid)
        other_chat = await make_chat(factory, uid, char_id, title="Elsewhere")
        async with factory() as session:
            result = await scopes.layered_preview(
                session, uid, chat_id=other_chat, messages=["fact"]
            )
            kinds = [s["scope"] for s in result["scopes"]]
            assert "chat" not in kinds
            assert "global" in kinds

    run(main())


def test_layered_preview_unowned_chat_is_none(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        async with factory() as session:
            assert await scopes.layered_preview(
                session, uid, chat_id="missing", messages=[]
            ) is None

    run(main())


def test_layered_preview_scope_budget_trims_only_its_layer(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id = await make_character(factory, uid)
        chat_id = await make_chat(factory, uid, char_id)
        from runmal.db.models import LoreEntry

        async with factory() as session:
            gbook = await make_book(factory, uid, "G")
            cbook = await make_book(factory, uid, "C")
            async with factory() as inner:
                inner.add(LoreEntry(
                    lorebook_id=gbook, user_id=uid, name="g1",
                    content="g" * 40, keys_json='["g"]',
                    secondary_keys_json="[]", constant=True,
                ))
                for name in ("c1", "c2"):
                    inner.add(LoreEntry(
                        lorebook_id=cbook, user_id=uid, name=name,
                        content="c" * 40, keys_json='["c"]',
                        secondary_keys_json="[]", constant=True,
                    ))
                await inner.commit()
            await scopes.assign_scope(session, uid, gbook, "global")
            await scopes.assign_scope(
                session, uid, cbook, "chat", owner_id=chat_id, token_budget=10
            )
            result = await scopes.layered_preview(
                session, uid, chat_id=chat_id, messages=["g c"]
            )
            by_scope = {s["scope"]: s for s in result["scopes"]}
            assert by_scope["global"]["included"] == 1
            assert by_scope["global"]["tokens_used"] == 10
            assert by_scope["chat"]["budget"] == 10
            assert by_scope["chat"]["included"] == 1
            assert by_scope["chat"]["discarded"] == 1
            assert by_scope["chat"]["tokens_used"] == 10
            reasons = {
                row["discard_reason"]
                for row in result["layers"]["chat"]["entries"]
                if row["status"] == "discarded"
            }
            assert reasons == {"scope_over_budget"}

    run(main())


def test_layered_preview_budget_zero_mutes_only_its_layer(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id, chat_id, books = await _seed_layered(factory, uid)
        async with factory() as session:
            await scopes.assign_scope(
                session, uid, books["chat"], "chat",
                owner_id=chat_id, token_budget=0,
            )
            result = await scopes.layered_preview(
                session, uid, chat_id=chat_id, messages=["fact"]
            )
            by_scope = {s["scope"]: s for s in result["scopes"]}
            assert by_scope["chat"]["included"] == 0
            assert by_scope["chat"]["tokens_used"] == 0
            assert by_scope["global"]["included"] == 1
            assert by_scope["persona"]["included"] == 1

    run(main())


def test_layered_preview_strictest_assignment_budget_wins(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        from runmal.db.models import LoreEntry

        async with factory() as session:
            first = await make_book(factory, uid, "A")
            second = await make_book(factory, uid, "B")
            async with factory() as inner:
                for bid, ch in ((first, "a"), (second, "b")):
                    inner.add(LoreEntry(
                        lorebook_id=bid, user_id=uid, name=ch,
                        content=ch * 40, keys_json=f'["{ch}"]',
                        secondary_keys_json="[]", constant=True,
                    ))
                await inner.commit()
            await scopes.assign_scope(
                session, uid, first, "global", token_budget=100
            )
            await scopes.assign_scope(
                session, uid, second, "global", token_budget=10
            )
            result = await scopes.layered_preview(session, uid, messages=["a b"])
            summary = result["scopes"][0]
            assert summary["scope"] == "global"
            assert summary["budget"] == 10
            assert summary["tokens_used"] <= 10

    run(main())


def test_layered_preview_shadowed_book_counted_once(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id = await make_character(factory, uid)
        chat_id = await make_chat(factory, uid, char_id)
        from runmal.db.models import LoreEntry

        async with factory() as session:
            bid = await make_book(factory, uid, "Shared")
            async with factory() as inner:
                inner.add(LoreEntry(
                    lorebook_id=bid, user_id=uid, name="shared fact",
                    content="shared lore content", keys_json='["fact"]',
                    secondary_keys_json="[]", constant=True,
                ))
                await inner.commit()
            await scopes.assign_scope(session, uid, bid, "global")
            await scopes.assign_scope(session, uid, bid, "chat", owner_id=chat_id)
            result = await scopes.layered_preview(
                session, uid, chat_id=chat_id, messages=["fact"]
            )
            kinds = [s["scope"] for s in result["scopes"]]
            assert kinds == ["chat"]
            assert result["shadowed"] == [
                {"book_id": bid, "kept_scope": "chat", "dropped_scope": "global"}
            ]
            assert result["scopes"][0]["included"] == 1

    run(main())


def test_layered_preview_binding_book_is_character_layer(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_id = await make_character(factory, uid)
        from runmal.db.models import LoreEntry
        from runmal.lorebooks.binding import bind_book

        async with factory() as session:
            bid = await make_book(factory, uid, "Bound")
            async with factory() as inner:
                inner.add(LoreEntry(
                    lorebook_id=bid, user_id=uid, name="bound fact",
                    content="bound lore content", keys_json='["fact"]',
                    secondary_keys_json="[]", constant=True,
                ))
                await inner.commit()
            await bind_book(session, uid, char_id, bid)
            result = await scopes.layered_preview(
                session, uid, character_id=char_id, messages=["fact"]
            )
            assert [s["scope"] for s in result["scopes"]] == ["character"]
            book_row = result["scopes"][0]["books"][0]
            assert book_row["via"] == "binding"
            assert book_row["lorebook_id"] == bid
            assert result["scopes"][0]["included"] == 1

    run(main())


def test_layered_preview_persona_override_changes_persona_layer(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await make_user(factory)
        char_a = await make_character(factory, uid, "A")
        char_b = await make_character(factory, uid, "B")
        chat_id = await make_chat(factory, uid, char_a)
        from runmal.db.models import LoreEntry

        async with factory() as session:
            bid = await make_book(factory, uid, "PersonaB")
            async with factory() as inner:
                inner.add(LoreEntry(
                    lorebook_id=bid, user_id=uid, name="pb fact",
                    content="persona b lore", keys_json='["fact"]',
                    secondary_keys_json="[]", constant=True,
                ))
                await inner.commit()
            await scopes.assign_scope(session, uid, bid, "persona", owner_id=char_b)
            plain = await scopes.layered_preview(
                session, uid, chat_id=chat_id, messages=["fact"]
            )
            assert [s["scope"] for s in plain["scopes"]] == []
            switched = await scopes.layered_preview(
                session, uid, chat_id=chat_id,
                persona_character_id=char_b, messages=["fact"],
            )
            assert [s["scope"] for s in switched["scopes"]] == ["persona"]

    run(main())


# ----------------------------------------------------------------------- REST


def test_rest_assign_get_unassign_scope(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = api_book(client, "World")
    put = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope",
        json={"scope_kind": "global", "token_budget": 50, "position": 2},
    )
    assert put.status_code == 201, put.text
    body = put.json()
    assert body["scope_kind"] == "global"
    assert body["owner_id"] == ""
    assert body["token_budget"] == 50
    assert body["lorebook"]["id"] == book["id"]

    listing = client.get(f"/api/v1/lorebooks/{book['id']}/scopes")
    assert listing.status_code == 200
    assert len(listing.json()["scopes"]) == 1

    layer = client.get("/api/v1/lore-scopes", params={"scope_kind": "global"})
    assert layer.status_code == 200
    assert len(layer.json()["scopes"]) == 1

    deleted = client.delete(
        f"/api/v1/lorebooks/{book['id']}/scope",
        params={"scope_kind": "global"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    again = client.delete(
        f"/api/v1/lorebooks/{book['id']}/scope",
        params={"scope_kind": "global"},
    )
    assert again.status_code == 404


def test_rest_assign_validation_and_ownership(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = api_book(client, "World")
    bad_kind = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope", json={"scope_kind": "world"}
    )
    assert bad_kind.status_code == 422
    missing_owner = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope", json={"scope_kind": "chat"}
    )
    assert missing_owner.status_code == 422
    missing_book = client.put(
        "/api/v1/lorebooks/missing/scope", json={"scope_kind": "global"}
    )
    assert missing_book.status_code == 404
    missing_chat = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope",
        json={"scope_kind": "chat", "owner_id": "missing"},
    )
    assert missing_chat.status_code == 404
    negative = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope",
        json={"scope_kind": "global", "token_budget": -5},
    )
    assert negative.status_code == 422
    scopes_404 = client.get("/api/v1/lorebooks/missing/scopes")
    assert scopes_404.status_code == 404


def test_rest_chat_scope_and_layered_preview(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = api_character(client)
    chat = client.post(
        "/api/v1/chats", json={"title": "Hall", "character_id": char["id"]}
    )
    assert chat.status_code == 201, chat.text
    chat_id = chat.json()["id"]
    book = api_book(
        client, "Pinned",
        entries=[const_entry("pinned fact", "pinned lore content")],
    )
    put = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope",
        json={"scope_kind": "chat", "owner_id": chat_id},
    )
    assert put.status_code == 201, put.text
    preview = client.post(
        f"/api/v1/chats/{chat_id}/lore-preview", json={"messages": ["fact"]}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["layered"] is True
    assert [s["scope"] for s in body["scopes"]] == ["chat"]
    assert body["scopes"][0]["included"] == 1
    missing = client.post(
        "/api/v1/chats/missing/lore-preview", json={"messages": []}
    )
    assert missing.status_code == 404


# -------------------------------------------------------------------- inspect


def test_inspect_with_chat_id_wires_scoped_layers(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = api_character(client)
    chat = client.post(
        "/api/v1/chats", json={"title": "Hall", "character_id": char["id"]}
    )
    chat_id = chat.json()["id"]
    book = api_book(
        client, "World",
        entries=[const_entry("world fact", "world lore content")],
    )
    put = client.put(
        f"/api/v1/lorebooks/{book['id']}/scope", json={"scope_kind": "global"}
    )
    assert put.status_code == 201
    resp = client.post(
        "/api/v1/debug/prompt-inspect",
        json={
            "character_id": char["id"],
            "chat_id": chat_id,
            "messages": ["fact"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "lore_scopes" in body
    assert [s["scope"] for s in body["lore_scopes"]["scopes"]] == ["global"]
    lore_slots = [
        s for s in body["slots"]
        if s["provenance"] == "lorebook:World@global" and s["status"] == "included"
    ]
    assert len(lore_slots) == 1
    assert lore_slots[0]["slot_id"].startswith("lore/global/")


def test_inspect_without_chat_id_has_no_lore_scopes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = api_character(client)
    book = api_book(
        client, "World",
        entries=[const_entry("world fact", "world lore content")],
    )
    client.put(
        f"/api/v1/lorebooks/{book['id']}/scope", json={"scope_kind": "global"}
    )
    resp = client.post(
        "/api/v1/debug/prompt-inspect",
        json={"character_id": char["id"], "messages": ["fact"]},
    )
    assert resp.status_code == 200, resp.text
    assert "lore_scopes" not in resp.json()


def test_inspect_with_missing_chat_is_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/debug/prompt-inspect",
        json={"chat_id": "missing", "messages": []},
    )
    assert resp.status_code == 404

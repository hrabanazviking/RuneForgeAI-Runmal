"""P-024 acceptance: library organisation — tags, favourites,
search, sort and pagination over the character library.

Service contract (runmal.library.organise): get_organisation,
set_tags, add_tags, remove_tag, set_favourite, list_library,
list_tags. HTTP contract (mounted /api/v1): GET /library/cards,
GET /library/tags, GET/PUT/POST/DELETE organisation routes.
Fixtures are authored fresh here; helper patterns mirror
test_p022_bulk_library_import.py.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.cards.models import CharacterCard
from runmal.characters.service import (
    create_character,
    create_character_from_card,
    delete_character,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Character, User
from runmal.db.owners import get_or_create_owner
from runmal.library import organise

# ---------------------------------------------------------------- helpers

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


def card_dict(name, tags=None, **over):
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A card authored for the organisation battery.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": list(tags or []),
        "creator": "forge",
        "extensions": {},
    }
    card.update(over)
    return card


async def make_card(factory, user_id, name, tags=None, **over) -> str:
    async with factory() as session:
        char = await create_character(
            session, user_id, card_dict(name, tags, **over)
        )
        return char.id


async def get_org(factory, user_id, character_id):
    async with factory() as session:
        return await organise.get_organisation(session, user_id, character_id)


async def do_set_tags(factory, user_id, character_id, tags):
    async with factory() as session:
        return await organise.set_tags(session, user_id, character_id, tags)


async def do_add_tags(factory, user_id, character_id, tags):
    async with factory() as session:
        return await organise.add_tags(session, user_id, character_id, tags)


async def do_remove_tag(factory, user_id, character_id, tag):
    async with factory() as session:
        return await organise.remove_tag(session, user_id, character_id, tag)


async def do_set_favourite(factory, user_id, character_id, value):
    async with factory() as session:
        return await organise.set_favourite(
            session, user_id, character_id, value
        )


async def list_lib(factory, user_id, **kw):
    kw.setdefault("limit", 100)
    kw.setdefault("offset", 0)
    async with factory() as session:
        return await organise.list_library(session, user_id, **kw)


def tag_rows(result):
    if isinstance(result, dict):
        return result.get("tags", [])
    return list(result)


async def list_tag_rows(factory, user_id):
    async with factory() as session:
        return tag_rows(await organise.list_tags(session, user_id))


_SORT_CANDIDATES = {
    "name_asc": ["name_asc", "name", "asc_name"],
    "name_desc": ["name_desc", "-name", "desc_name"],
    "newest": ["newest", "created_desc", "recent"],
    "oldest": ["oldest", "created_asc"],
    "favourites_first": [
        "favourites_first",
        "favorites_first",
        "favourite_first",
    ],
}


async def list_sorted(factory, user_id, logical, **kw):
    last_exc = None
    for candidate in _SORT_CANDIDATES[logical]:
        try:
            return await list_lib(factory, user_id, sort=candidate, **kw)
        except Exception as exc:  # unknown spelling: try the next one
            last_exc = exc
    raise AssertionError(f"no accepted sort spelling for {logical}: {last_exc}")


def item_names(result):
    return [item["name"] for item in result["items"]]


def item_ids(result):
    return [item["id"] for item in result["items"]]


def lower_tags(org):
    return sorted(t.lower() for t in org["tags"])


# ------------------------------------------------------- seeding & storage

async def test_imported_card_tags_seed_organisation(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "Seeded", tags=["alpha", "Beta"])
    org = await get_org(factory, user_id, cid)
    assert org is not None
    assert org["character_id"] == cid
    assert org["name"] == "Seeded"
    assert lower_tags(org) == ["alpha", "beta"]
    assert org["is_favourite"] is False


async def test_set_tags_persists_and_updates_card_json(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "Keeper", tags=["old"])
    await do_set_tags(factory, user_id, cid, ["Shiny", "New"])
    org = await get_org(factory, user_id, cid)
    assert lower_tags(org) == ["new", "shiny"]
    async with factory() as session:
        row = (
            await session.execute(
                select(Character).where(Character.id == cid)
            )
        ).scalar_one()
        stored = json.loads(row.card_json)
    data = stored.get("data") if isinstance(stored.get("data"), dict) else stored
    assert sorted(t.lower() for t in data.get("tags", [])) == ["new", "shiny"]


async def test_set_tags_preserves_unknown_card_fields(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    raw_card = card_dict(
        "Mystery",
        tags=["old"],
        extensions={"x-test": {"keep": 1}},
    )
    raw_card["x_custom_field"] = {"keep": 7}
    async with factory() as session:
        char = Character(
            user_id=user_id,
            name="Mystery",
            card_json=json.dumps(raw_card),
        )
        session.add(char)
        await session.commit()
        cid = char.id
    await do_set_tags(factory, user_id, cid, ["fresh"])
    async with factory() as session:
        row = (
            await session.execute(
                select(Character).where(Character.id == cid)
            )
        ).scalar_one()
        blob = row.card_json
    stored = json.loads(blob)
    data = stored.get("data") if isinstance(stored.get("data"), dict) else stored
    assert [t.lower() for t in data.get("tags", [])] == ["fresh"]
    def _walk(obj):
        if isinstance(obj, dict):
            yield obj
            for value in obj.values():
                yield from _walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from _walk(value)

    dicts = list(_walk(stored))
    assert any(d.get("x-test") == {"keep": 1} for d in dicts)
    assert any(d.get("x_custom_field") == {"keep": 7} for d in dicts)
    org = await get_org(factory, user_id, cid)
    assert [t.lower() for t in org["tags"]] == ["fresh"]


# ------------------------------------------------------------- validation

async def test_tag_normalisation_collapses_and_dedupes(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "Norm")
    await do_set_tags(
        factory,
        user_id,
        cid,
        ["  Fantasy   World ", "fantasy world", "FANTASY   WORLD", "Quest"],
    )
    org = await get_org(factory, user_id, cid)
    assert len(org["tags"]) == 2
    assert lower_tags(org) == ["fantasy world", "quest"]
    assert all(t == " ".join(t.split()) for t in org["tags"])
    assert all(t == t.strip() for t in org["tags"])


async def test_empty_tag_raises_value_error(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "EmptyTag")
    with pytest.raises(ValueError):
        await do_set_tags(factory, user_id, cid, [""])
    with pytest.raises(ValueError):
        await do_set_tags(factory, user_id, cid, ["ok", "   "])


async def test_overlong_tag_raises_value_error(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "LongTag")
    with pytest.raises(ValueError):
        await do_set_tags(factory, user_id, cid, ["x" * 65])
    await do_set_tags(factory, user_id, cid, ["x" * 64])
    org = await get_org(factory, user_id, cid)
    assert org["tags"] == ["x" * 64]


async def test_too_many_tags_raise_value_error(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "ManyTags")
    with pytest.raises(ValueError):
        await do_set_tags(
            factory, user_id, cid, [f"tag-{i}" for i in range(51)]
        )


# ------------------------------------------------------------ add / remove

async def test_add_tags_unions_without_duplicates(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "Union", tags=["one", "two"])
    await do_add_tags(factory, user_id, cid, ["Two", "three"])
    org = await get_org(factory, user_id, cid)
    assert lower_tags(org) == ["one", "three", "two"]
    await do_add_tags(factory, user_id, cid, ["ONE"])
    org = await get_org(factory, user_id, cid)
    assert lower_tags(org) == ["one", "three", "two"]


async def test_remove_tag_case_insensitive_and_absent_noop(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(
        factory, user_id, "Removable", tags=["Fantasy", "Quest"]
    )
    await do_remove_tag(factory, user_id, cid, "fantasy")
    org = await get_org(factory, user_id, cid)
    assert lower_tags(org) == ["quest"]
    await do_remove_tag(factory, user_id, cid, "not-there")
    org = await get_org(factory, user_id, cid)
    assert lower_tags(org) == ["quest"]


# ------------------------------------------------- favourites, filters, q

async def test_favourite_persists_and_filter(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    fav = await make_card(factory, user_id, "Favoured")
    plain = await make_card(factory, user_id, "Plain")
    await do_set_favourite(factory, user_id, fav, True)
    org = await get_org(factory, user_id, fav)
    assert org["is_favourite"] is True
    result = await list_lib(factory, user_id, favourites_only=True)
    assert result["total"] == 1
    assert item_ids(result) == [fav]
    assert result["items"][0]["is_favourite"] is True
    await do_set_favourite(factory, user_id, fav, False)
    org = await get_org(factory, user_id, fav)
    assert org["is_favourite"] is False
    result = await list_lib(factory, user_id, favourites_only=True)
    assert result["total"] == 0
    result = await list_lib(factory, user_id)
    assert result["total"] == 2
    assert plain in item_ids(result)


async def test_tag_filter_any_vs_all(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    both = await make_card(factory, user_id, "Both", tags=["red", "round"])
    red = await make_card(factory, user_id, "RedOnly", tags=["red"])
    rnd = await make_card(factory, user_id, "RoundOnly", tags=["round"])
    await make_card(factory, user_id, "Neither", tags=["blue"])
    any_res = await list_lib(
        factory, user_id, tags=["red", "round"], tag_mode="any"
    )
    assert any_res["total"] == 3
    assert set(item_ids(any_res)) == {both, red, rnd}
    all_res = await list_lib(
        factory, user_id, tags=["RED", "Round"], tag_mode="all"
    )
    assert all_res["total"] == 1
    assert item_ids(all_res) == [both]


async def test_search_matches_name_and_tag_case_insensitively(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    by_name = await make_card(factory, user_id, "Dragon Queen", tags=["royal"])
    by_tag = await make_card(
        factory, user_id, "Plain Knight", tags=["dragon-lore"]
    )
    await make_card(factory, user_id, "Quiet Baker", tags=["cozy"])
    result = await list_lib(factory, user_id, q="dragon")
    assert result["total"] == 2
    assert set(item_ids(result)) == {by_name, by_tag}
    result = await list_lib(factory, user_id, q="QUEEN")
    assert item_ids(result) == [by_name]
    result = await list_lib(factory, user_id, q="zzz-no-match")
    assert result["total"] == 0
    assert result["items"] == []


# --------------------------------------------------------- sorts & paging

async def test_sort_by_name_ascending_and_descending(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    for name in ("Bravo", "Alpha", "Charlie"):
        await make_card(factory, user_id, name)
    asc = await list_sorted(factory, user_id, "name_asc")
    assert item_names(asc) == ["Alpha", "Bravo", "Charlie"]
    desc = await list_sorted(factory, user_id, "name_desc")
    assert item_names(desc) == ["Charlie", "Bravo", "Alpha"]


async def test_sort_newest_and_oldest(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    ids = {}
    for name in ("First Made", "Second Made", "Third Made"):
        ids[name] = await make_card(factory, user_id, name)
    base = datetime(2024, 1, 1, 12, 0, 0)
    async with factory() as session:
        rows = (
            await session.execute(select(Character))
        ).scalars().all()
        for row in rows:
            age = {"First Made": 0, "Second Made": 1, "Third Made": 2}[row.name]
            row.created_at = base + timedelta(days=age)
        await session.commit()
    newest = await list_sorted(factory, user_id, "newest")
    assert item_names(newest) == ["Third Made", "Second Made", "First Made"]
    oldest = await list_sorted(factory, user_id, "oldest")
    assert item_names(oldest) == ["First Made", "Second Made", "Third Made"]


async def test_sort_favourites_first(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    await make_card(factory, user_id, "Alpha Plain")
    fav = await make_card(factory, user_id, "Zulu Favoured")
    await make_card(factory, user_id, "Mid Plain")
    await do_set_favourite(factory, user_id, fav, True)
    result = await list_sorted(factory, user_id, "favourites_first")
    assert result["items"][0]["id"] == fav
    assert result["items"][0]["is_favourite"] is True
    assert all(
        item["is_favourite"] is False for item in result["items"][1:]
    )


async def test_pagination_slices_with_honest_total(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    for i in range(7):
        await make_card(factory, user_id, f"Paged-{i}")
    page1 = await list_sorted(factory, user_id, "name_asc", limit=3, offset=0)
    page2 = await list_sorted(factory, user_id, "name_asc", limit=3, offset=3)
    page3 = await list_sorted(factory, user_id, "name_asc", limit=3, offset=6)
    assert (len(page1["items"]), len(page2["items"]), len(page3["items"])) == (3, 3, 1)
    assert page1["total"] == page2["total"] == page3["total"] == 7
    seen = item_ids(page1) + item_ids(page2) + item_ids(page3)
    assert len(set(seen)) == 7
    beyond = await list_lib(factory, user_id, limit=3, offset=99)
    assert beyond["total"] == 7
    assert beyond["items"] == []


async def test_list_tags_counts_across_cards(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    await make_card(factory, user_id, "One", tags=["red", "round"])
    await make_card(factory, user_id, "Two", tags=["red"])
    await make_card(factory, user_id, "Three", tags=["Red", "solo"])
    await make_card(factory, user_id, "Four")
    rows = await list_tag_rows(factory, user_id)
    by_key = {row["tag_key"]: row for row in rows}
    assert by_key["red"]["count"] == 3
    assert by_key["round"]["count"] == 1
    assert by_key["solo"]["count"] == 1
    assert by_key["red"]["tag"].lower() == "red"
    assert len(rows) == 3


# ------------------------------------------------- isolation & lifecycle

async def test_cross_user_isolation(tmp_path):
    factory = make_factory(tmp_path)
    user_a = await make_user(factory, "alice")
    user_b = await make_user(factory, "bob")
    cid = await make_card(factory, user_a, "Alice Card", tags=["hers"])
    assert await get_org(factory, user_b, cid) is None
    assert (await list_lib(factory, user_b))["total"] == 0
    assert await list_tag_rows(factory, user_b) == []
    for act in (
        lambda: do_set_tags(factory, user_b, cid, ["stolen"]),
        lambda: do_add_tags(factory, user_b, cid, ["stolen"]),
        lambda: do_remove_tag(factory, user_b, cid, "hers"),
        lambda: do_set_favourite(factory, user_b, cid, True),
    ):
        try:
            await act()
        except Exception:
            pass  # a refusal is also isolation; state is what matters
    org = await get_org(factory, user_a, cid)
    assert lower_tags(org) == ["hers"]
    assert org["is_favourite"] is False


async def test_unknown_card_organisation_is_none(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    await make_card(factory, user_id, "Real Card")
    assert await get_org(factory, user_id, "no-such-card-id") is None


async def test_soft_deleted_character_is_hidden(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cid = await make_card(factory, user_id, "Doomed", tags=["gone"])
    keep = await make_card(factory, user_id, "Survivor", tags=["here"])
    async with factory() as session:
        assert await delete_character(session, user_id, cid) is True
    assert await get_org(factory, user_id, cid) is None
    result = await list_lib(factory, user_id)
    assert result["total"] == 1
    assert item_ids(result) == [keep]
    rows = await list_tag_rows(factory, user_id)
    assert {row["tag_key"] for row in rows} == {"here"}


# ------------------------------------------------------------------ scale

async def test_scale_three_hundred_cards(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    ids = []
    async with factory() as session:
        for i in range(300):
            char = await create_character_from_card(
                session,
                user_id,
                CharacterCard(
                    name=f"Card-{i:03d}",
                    description="scale seed",
                    tags=[f"genre-{i % 10}", "common"],
                ),
                commit=False,
            )
            ids.append(char.id)
        await session.commit()
    async with factory() as session:
        for i in range(0, 300, 25):
            await organise.set_favourite(session, user_id, ids[i], True)
    assert (await list_lib(factory, user_id, limit=1))["total"] == 300
    common = await list_lib(factory, user_id, tags=["common"], limit=1)
    assert common["total"] == 300
    genre = await list_lib(factory, user_id, tags=["genre-3"], limit=1)
    assert genre["total"] == 30
    favs = await list_lib(factory, user_id, favourites_only=True, limit=1)
    assert favs["total"] == 12
    found = await list_lib(factory, user_id, q="Card-29", limit=50)
    assert found["total"] == 10  # Card-290 .. Card-299 only
    seen = []
    for offset in range(0, 300, 50):
        page = await list_lib(factory, user_id, limit=50, offset=offset)
        assert len(page["items"]) == 50
        assert page["total"] == 300
        seen.extend(item_ids(page))
    assert len(set(seen)) == 300
    rows = await list_tag_rows(factory, user_id)
    by_key = {row["tag_key"]: row["count"] for row in rows}
    assert by_key["common"] == 300
    assert all(by_key[f"genre-{i}"] == 30 for i in range(10))


# ---------------------------------------------------------------- HTTP API

@pytest.fixture()
def http(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def http_owner_id(factory) -> str:
    async def _owner():
        async with factory() as session:
            return (await get_or_create_owner(session)).id

    return asyncio.run(_owner())


def http_card(factory, user_id, name, tags=None) -> str:
    async def _make():
        async with factory() as session:
            char = await create_character(
                session, user_id, card_dict(name, tags)
            )
            return char.id

    return asyncio.run(_make())


def test_http_tags_and_favourite_round_trip(http):
    client, factory = http
    uid = http_owner_id(factory)
    cid = http_card(factory, uid, "Web Card", tags=["seed"])
    resp = client.put(f"/api/v1/library/cards/{cid}/tags", json={"tags": ["Web", "Quest"]})
    assert resp.status_code == 200
    resp = client.get(f"/api/v1/library/cards/{cid}/organisation")
    assert resp.status_code == 200
    org = resp.json()
    assert org["character_id"] == cid
    assert sorted(t.lower() for t in org["tags"]) == ["quest", "web"]
    assert org["is_favourite"] is False
    resp = client.post(f"/api/v1/library/cards/{cid}/tags", json={"tags": ["Extra"]})
    assert resp.status_code == 200
    resp = client.delete(f"/api/v1/library/cards/{cid}/tags/quest")
    assert resp.status_code == 200
    org = client.get(f"/api/v1/library/cards/{cid}/organisation").json()
    assert sorted(t.lower() for t in org["tags"]) == ["extra", "web"]
    resp = client.put(f"/api/v1/library/cards/{cid}/favourite", json={"is_favourite": True})
    assert resp.status_code == 200
    org = client.get(f"/api/v1/library/cards/{cid}/organisation").json()
    assert org["is_favourite"] is True


def test_http_list_filter_search_and_tags_index(http):
    client, factory = http
    uid = http_owner_id(factory)
    http_card(factory, uid, "Harbour Light", tags=["sea", "calm"])
    http_card(factory, uid, "Mountain Ash", tags=["sea"])
    http_card(factory, uid, "Inland Pine", tags=["forest"])
    resp = client.get("/api/v1/library/cards", params={"tag": "sea"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 2
    assert {i["name"] for i in payload["items"]} == {"Harbour Light", "Mountain Ash"}
    resp = client.get("/api/v1/library/cards", params={"q": "pine"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/v1/library/tags")
    assert resp.status_code == 200
    rows = {r["tag_key"]: r["count"] for r in resp.json()["tags"]}
    assert rows == {"sea": 2, "calm": 1, "forest": 1}


def test_http_invalid_sort_is_422(http):
    client, _factory = http
    resp = client.get("/api/v1/library/cards", params={"sort": "bogus-sort"})
    assert resp.status_code == 422


def test_http_unknown_card_is_404(http):
    client, _factory = http
    missing = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/v1/library/cards/{missing}/organisation")
    assert resp.status_code == 404
    resp = client.put(f"/api/v1/library/cards/{missing}/tags", json={"tags": ["x"]})
    assert resp.status_code == 404
    resp = client.put(f"/api/v1/library/cards/{missing}/favourite", json={"is_favourite": True})
    assert resp.status_code == 404


def test_http_invalid_tag_payload_is_422(http):
    client, factory = http
    uid = http_owner_id(factory)
    cid = http_card(factory, uid, "Strict Card")
    resp = client.put(f"/api/v1/library/cards/{cid}/tags", json={"tags": [""]})
    assert resp.status_code == 422
    resp = client.put(f"/api/v1/library/cards/{cid}/tags", json={"tags": ["x" * 65]})
    assert resp.status_code == 422
    org = client.get(f"/api/v1/library/cards/{cid}/organisation").json()
    assert org["tags"] == []

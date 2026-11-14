"""R-08 acceptance (live engine): the Characters library + editor
roads against the real in-process engine on a fresh data dir —
full-card read/edit with unknown-field preservation, tags and
favourites through the library, avatar + asset byte round trips,
character-book + lorebook binding, version history with the
composed restore, duplicate, soft-delete with undo, export and
bulk import.

No Qt here (the widgets are driven by
``scripts/desktop_r08_proof.py`` and ``test_r08_desktop_window.py``).
"""

import json

import pytest

from runmal.desktop.character_logic import CharacterFlow
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState

# A real 1x1 PNG (the smallest valid image the avatar road accepts).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da6364f8cf500f00038601805a347d6b"
    "0000000049454e44ae426082"
)

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "mes_example": "<START>\nKeeper: State your name.",
    "post_history_instructions": "Stay terse.",
    "first_mes": "Well met, traveller. The pass is open.",
    "alternate_greetings": ["Well met. State your name, traveller."],
    "creator_notes": "A keeper for the pass.",
    "tags": ["guard"],
    "creator": "Yrsa",
    "character_version": "1.0",
    "character_book": {
        "name": "Pass Lore",
        "entries": [
            {
                "keys": ["pass"],
                "content": "The pass opens at dawn.",
                "enabled": True,
            }
        ],
    },
    "extensions": {"r08_custom": {"keep": True}},
}


@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    yield handle
    handle.stop()


def make_client(handle) -> RunmalClient:
    return RunmalClient(DesktopSession.from_local_credential(handle.base_url))


def seed(client: RunmalClient):
    return client.create_character(dict(CARD), name="Gate Keeper")


def test_full_card_round_trip_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow = CharacterFlow(client)
        created = seed(client)
        card = client.get_character_card(created.id)
        assert card.description == "Guards the high pass."
        assert card.system_prompt == "You guard the high pass."
        assert card.first_mes.startswith("Well met")
        assert card.alternate_greetings == [
            "Well met. State your name, traveller."
        ]
        assert card.creator == "Yrsa"
        # The embedded character book materialised as a binding.
        bundle = flow.open_editor(created.id)
        assert bundle.book_entry_count >= 1
        assert bundle.binding.bound is True

        edits = {
            "name": "Gate Keeper",
            "description": "Now guards the LOW pass.",
            "personality": card.personality,
            "scenario": card.scenario,
            "system_prompt": card.system_prompt,
            "mes_example": card.mes_example,
            "post_history_instructions": card.post_history_instructions,
            "first_mes": card.first_mes,
            "creator_notes": card.creator_notes,
            "creator": card.creator,
            "character_version": "2.0",
            "nickname": card.nickname,
            "alternate_greetings": card.alternate_greetings,
        }
        saved = flow.save_character(card, edits, ["guard", "low-pass"])
        assert saved.description == "Now guards the LOW pass."
        assert saved.character_version == "2.0"
        # INV-009: the unknown extension survived the save. (The
        # real stored shape for an API-created card is the flat v2
        # form — fields at top level, not under "data".)
        from runmal.desktop.client.models import card_data_of

        assert card_data_of(saved.raw_card)["extensions"]["r08_custom"] == {
            "keep": True
        }
        assert flow.organisation(created.id).tags == ["guard", "low-pass"]

        # Library: search + favourites over the real organisation rows.
        total, items = flow.library(q="keeper")
        assert total == 1 and items[0].id == created.id
        flow.set_favourite(created.id, True)
        total, items = flow.library(favourites_only=True)
        assert total == 1 and items[0].is_favourite is True
        assert any(t.tag == "low-pass" for t in flow.library_tags())
    finally:
        client.close()


def test_avatar_assets_versions_delete_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow = CharacterFlow(client)
        created = seed(client)

        # Avatar bytes round-trip through the real roads.
        stored = flow.set_avatar(created.id, "keeper.png", PNG_BYTES)
        assert stored == "keeper.png"
        data, media = flow.avatar_bytes(created.id)
        assert data == PNG_BYTES and media == "image/png"
        assert client.get_character(created.id).has_avatar is True

        # A manual asset upload lands in the asset list.
        asset = flow.add_asset(created.id, "pass-map.png", PNG_BYTES)
        assert asset.status == "stored"
        assert any(a.id == asset.id for a in flow.assets(created.id))
        content, _media = client.get_asset_bytes(created.id, asset.id)
        assert content == PNG_BYTES

        # Versions: a same-name, different-content create is v2 in
        # the same lineage; the composed restore puts v1's card
        # back as the v2 row's current card.
        second = client.create_character(
            {**CARD, "description": "Second telling."}, name="Gate Keeper"
        )
        assert second.id != created.id and second.version_no == 2
        history = flow.versions(created.id)
        assert history.latest_version_no == 2
        assert [v.version_no for v in history.versions] == [1, 2]
        restored = flow.restore_version(second.id, 1)
        assert restored.description == "Guards the high pass."

        # Duplicate, then soft-delete + undo.
        clone = flow.duplicate(created.id)
        assert clone.name == "Gate Keeper (copy)"
        assert flow.delete(clone.id) is True
        assert all(c.id != clone.id for c in client.list_characters())
        back = flow.undo_delete(clone.id)
        assert back.id == clone.id

        # Export is the stored card, re-importable JSON.
        document = json.loads(flow.export_text(created.id))
        data_level = document.get("data", document)
        assert data_level["name"] == "Gate Keeper"

        # Bulk import of a fresh card file lands a new character.
        ferry_card = json.dumps({
            "spec": "chara_card_v2", "spec_version": "2.0",
            "data": {"name": "Ferryman", "description": "Rows the river."},
        }).encode()
        outcome = flow.import_files([("ferryman.json", ferry_card)])
        assert outcome.created_ids, outcome.lines
        assert any(
            c.name == "Ferryman" for c in client.list_characters()
        )
    finally:
        client.close()


def test_binding_to_a_world_lorebook_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow = CharacterFlow(client)
        created = client.create_character(
            {"name": "Sage", "description": "Knows things."}, name="Sage"
        )
        # A world lorebook made through the raw road the R-10
        # editor will own; here it is only the binding target.
        import httpx

        session = DesktopSession.from_local_credential(live_engine.base_url)
        with httpx.Client(
            base_url=live_engine.base_url, trust_env=False
        ) as http:
            session.apply(http)
            made = http.post(
                "/api/v1/lorebooks",
                json={"name": "World Facts", "description": "Things."},
            )
            assert made.status_code == 201, made.text
            book_id = made.json()["id"]
        bound = flow.bind(created.id, book_id, precedence="world_first")
        assert bound.bound is True and bound.lorebook_id == book_id
        assert bound.precedence == "world_first"
        assert flow.unbind(created.id) is True
        assert client.get_lorebook_binding(created.id).bound is False
    finally:
        client.close()

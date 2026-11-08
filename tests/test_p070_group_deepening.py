"""P-070 acceptance: group chats deepened — activation strategies on
the persistent room road, per-member overrides, group lore/persona
handling (delta census ST-11 depth, ST-13, ST-14).

Contract under test:
- The deepening document lives in groups.speaker_config under "p070"
  (no migration taken by P-070; head was 0038 on its base and
  is 0039 in the merged tree after P-073; S211 keys order/seed untouched),
  is validated (bad mode/activation/max_turns/unknown keys -> 422),
  and defaults are complete.
- select via POST /groups/{id}/next honours the stored strategy:
  natural (mention + seeded weighted), list (persisted cursor
  advances across calls), pooled (persisted pool drains then
  resets), manual (designation only).
- Per-member overrides: force pre-empts natural/list/pooled; never
  excludes everywhere including a manual designation; muted still
  absolute; allow_self_responses=false stops an immediate repeat
  when someone else can speak, true permits it.
- Persona handling: swap puts only the speaker's persona in the
  system prompt; join merges every member with the join prefix/
  suffix templates ({{char}}), marks the speaker, appends the group
  scenario once and drops card scenarios; the group scenario
  override replaces the card scenario in swap; a persona_override
  replaces the card persona for the room only (card unchanged,
  proven via peek + a fresh group).
- Group lore: a character-scoped lorebook's constant entry rides
  the generated prompt for its member; lore_enabled=false drops
  the character layer for that member.
- Peek reads member + override + effective persona without
  mutating the card. Generation lands via the transcript with the
  speaker snapshot and metadata-only events. Run is bounded and
  capped by auto_mode.max_turns when enabled. Unknown group /
  member -> 404; overrides for non-members -> 422.
"""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.groupchat.deepening import (
    build_prompt_messages,
    default_deepening,
    normalise_deepening,
    select_next_pure,
)
from runmal.groupchat.policies import MemberState

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0041"  # P-070 takes no migration; head is P-073's 0039
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_character(client, name, personality=None, scenario=None):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    if personality is not None:
        card["personality"] = personality
    if scenario is not None:
        card["scenario"] = scenario
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_group(client, members, policy=None):
    resp = client.post(
        "/api/v1/groups", json={"name": "Mead Hall", "member_character_ids": list(members)}
    )
    assert resp.status_code == 201, resp.text
    group = resp.json()
    if policy:
        upd = client.patch(f"/api/v1/groups/{group['id']}", json={"speaker_policy": policy})
        assert upd.status_code == 200, upd.text
    return group


def put_deepening(client, gid, doc):
    resp = client.put(f"/api/v1/groups/{gid}/deepening", json=doc)
    assert resp.status_code == 200, resp.text
    return resp.json()


def post_user(client, gid, text):
    resp = client.post(
        f"/api/v1/groups/{gid}/messages", json={"speaker": "user", "content": text}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def next_turn(client, gid, **kw):
    resp = client.post(f"/api/v1/groups/{gid}/next", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


# -- pure: document validation -------------------------------------------


def test_normalise_defaults_and_validation():
    doc = normalise_deepening(None)
    assert doc == default_deepening()
    assert doc["generation_mode"] == "swap"
    assert doc["allow_self_responses"] is False
    assert doc["auto_mode"] == {"enabled": False, "max_turns": 3}
    for bad in (
        {"generation_mode": "merge"},
        {"auto_mode": {"max_turns": 0}},
        {"auto_mode": {"max_turns": 11}},
        {"bogus": 1},
        {"member_overrides": {"c1": {"activation": "loud"}}},
        {"member_overrides": {"c1": {"lore_enabled": "yes"}}},
        {"state": {"list_cursor": -1}},
    ):
        with pytest.raises(ValueError):
            normalise_deepening(bad)


# -- pure: selection -------------------------------------------------------


def _members():
    return [
        MemberState("c-a", "Asta", talkativeness=0.9),
        MemberState("c-b", "Bryn", talkativeness=0.5),
        MemberState("c-c", "Kol", talkativeness=0.1),
    ]


def _deep(**kw):
    doc = default_deepening()
    doc.update(kw)
    return doc


def test_pure_force_and_never():
    deep = _deep(member_overrides={
        "c-c": {"activation": "force", "persona_override": None, "lore_enabled": True},
        "c-a": {"activation": "never", "persona_override": None, "lore_enabled": True},
    })
    picked, reason, _ = select_next_pure(
        _members(), policy_name="natural", speaker_config={"seed": 3},
        deepening=deep, history_speakers=[],
    )
    assert (picked, reason) == ("c-c", "forced")
    # never also silences a manual designation
    picked, reason, _ = select_next_pure(
        _members(), policy_name="manual", speaker_config={},
        deepening=deep, history_speakers=[], manual_speaker_id="c-a",
    )
    assert picked is None and reason == "manual_speaker_never"


def test_pure_self_response_rule():
    deep = _deep()
    picked, _, _ = select_next_pure(
        _members(), policy_name="list",
        speaker_config={"order": ["c-a", "c-b"]},
        deepening=deep, history_speakers=["user", "c-a"],
    )
    assert picked == "c-b"  # Asta just spoke; list would repeat her
    deep2 = _deep(allow_self_responses=True)
    picked, _, state = select_next_pure(
        _members(), policy_name="list",
        speaker_config={"order": ["c-a", "c-b"]},
        deepening=deep2, history_speakers=["user", "c-a"],
    )
    assert picked == "c-a"
    assert state["list_cursor"] == 1


def test_pure_prompt_shapes():
    roster = [
        {"character_id": "c-a", "name": "Asta",
         "manifest": {"personality": "Bold.", "scenario": "Card hall."},
         "override": {"activation": "default", "persona_override": None, "lore_enabled": True}},
        {"character_id": "c-b", "name": "Bryn",
         "manifest": {"personality": "Calm.", "scenario": "Card shore."},
         "override": {"activation": "default", "persona_override": None, "lore_enabled": True}},
    ]
    history = [
        {"role": "user", "speaker_id": None, "speaker_name": None, "content": "Hail."},
        {"role": "assistant", "speaker_id": "c-b", "speaker_name": "Bryn", "content": "Well met."},
    ]
    swap = build_prompt_messages("c-a", roster, _deep(), history, [])
    system = swap[0]["content"]
    assert "Bold." in system and "Calm." not in system
    assert "Card hall." in system
    assert swap[1] == {"role": "user", "content": "Hail."}
    assert swap[2] == {"role": "user", "content": "Bryn: Well met."}

    join = build_prompt_messages(
        "c-a", roster,
        _deep(generation_mode="join", join_prefix="<{{char}}>", join_suffix="</>",
              scenario_override="Group moot."),
        history, ["The moot is old."],
    )
    system = join[0]["content"]
    assert "<Asta>Bold.</>" in system and "<Bryn>Calm.</>" in system
    assert "[Now speaking: Asta]" in system
    assert "Card hall." not in system and "Card shore." not in system
    assert system.count("Group moot.") == 1
    assert "Group lore:\nThe moot is old." in system


# -- API: deepening document ----------------------------------------------


def test_deepening_roundtrip_and_s211_keys_untouched(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = make_group(client, [a, b])
    gid = group["id"]
    upd = client.patch(
        f"/api/v1/groups/{gid}",
        json={"speaker_policy": "list", "speaker_config": {"order": [a, b], "seed": 5}},
    )
    assert upd.status_code == 200
    doc = put_deepening(client, gid, {"generation_mode": "join", "join_prefix": "[{{char}}]"})
    assert doc["generation_mode"] == "join"
    assert doc["join_prefix"] == "[{{char}}]"
    fetched = client.get(f"/api/v1/groups/{gid}/deepening")
    assert fetched.status_code == 200 and fetched.json() == doc
    group_after = client.get(f"/api/v1/groups/{gid}").json()
    assert group_after["speaker_config"]["order"] == [a, b]
    assert group_after["speaker_config"]["seed"] == 5
    assert group_after["speaker_config"]["p070"]["generation_mode"] == "join"

    bad = client.put(f"/api/v1/groups/{gid}/deepening", json={"generation_mode": "merge"})
    assert bad.status_code == 422
    ghost = client.put(
        f"/api/v1/groups/{gid}/deepening",
        json={"member_overrides": {"nope": {"activation": "force"}}},
    )
    assert ghost.status_code == 422
    assert client.get("/api/v1/groups/nope/deepening").status_code == 404


# -- API: activation on the room road --------------------------------------


def test_list_cursor_persists_across_calls(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = make_group(client, [a, b], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a, b]}})
    put_deepening(client, gid, {"allow_self_responses": True})
    seq = [next_turn(client, gid)["speaker_id"] for _ in range(3)]
    assert seq == [a, b, a]


def test_pooled_pool_persists_and_resets(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = make_group(client, [a, b], policy="pooled")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"seed": 2}})
    put_deepening(client, gid, {"allow_self_responses": True})
    first = next_turn(client, gid)
    second = next_turn(client, gid)
    assert {first["speaker_id"], second["speaker_id"]} == {a, b}  # pool drains
    assert second["state"]["pool_spoken"] == []  # reset after full round
    third = next_turn(client, gid)
    assert third["speaker_id"] in {a, b}


def test_natural_mention_and_manual(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    k = make_character(client, "Kol")
    group = make_group(client, [a, k])  # natural by default
    gid = group["id"]
    result = next_turn(client, gid, user_text="@Kol, your craft?")
    assert result["speaker_id"] == k and result["reason"] == "natural_mention"

    upd = client.patch(f"/api/v1/groups/{gid}", json={"speaker_policy": "manual"})
    assert upd.status_code == 200
    assert next_turn(client, gid)["speaker_id"] is None  # no designation
    picked = next_turn(client, gid, manual_speaker_id=a)
    assert picked["speaker_id"] == a and picked["reason"] == "manual"


def test_force_never_muted_via_api(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    k = make_character(client, "Kol")
    group = make_group(client, [a, b, k])
    gid = group["id"]
    resp = client.patch(
        f"/api/v1/groups/{gid}/members/{k}/override", json={"activation": "force"}
    )
    assert resp.status_code == 200 and resp.json()["activation"] == "force"
    assert next_turn(client, gid)["speaker_id"] == k

    client.patch(f"/api/v1/groups/{gid}/members/{k}/override", json={"activation": "never"})
    client.patch(f"/api/v1/groups/{gid}/members/{a}/override", json={"activation": "force"})
    # Bryn muted, Asta forced, Kol never -> Asta, and muting Asta too is silence
    client.patch(f"/api/v1/groups/{gid}/members/{b}", json={"muted": True})
    assert next_turn(client, gid)["speaker_id"] == a
    client.patch(f"/api/v1/groups/{gid}/members/{a}", json={"muted": True})
    result = next_turn(client, gid)
    assert result["speaker_id"] is None and result["reason"] == "no_eligible_members"
    assert client.patch(
        f"/api/v1/groups/{gid}/members/nope/override", json={"activation": "force"}
    ).status_code == 404


# -- API: generation + persona/lore ----------------------------------------


def test_generate_lands_with_speaker_and_metadata_events(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta", personality="Bold and loud.")
    b = make_character(client, "Bryn", personality="Calm and soft.")
    group = make_group(client, [a, b], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a, b]}})
    result = next_turn(client, gid, user_text="Speak, friends.", generate=True)
    assert result["speaker_id"] == a
    message = result["message"]
    assert message["speaker_id"] == a and message["speaker_name"] == "Asta"
    assert message["content"]  # fake backend stub text still lands
    system = result["prompt"][0]["content"]
    assert "Bold and loud." in system and "Calm and soft." not in system  # swap
    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    assert [m["content"] for m in transcript][-1] == message["content"]
    # metadata-only events: kinds recorded, generated text never in data
    import asyncio

    from sqlalchemy import select

    from runmal.db.models import ChatEvent

    async def read_events():
        engine = create_db_engine(tmp_path / "test.db")
        factory = create_session_factory(engine)
        async with factory() as session:
            rows = await session.execute(
                select(ChatEvent).where(ChatEvent.chat_id == group["chat_id"])
            )
            return [(e.kind, e.data) for e in rows.scalars()]

    recorded = asyncio.run(read_events())
    kinds = [k for k, _ in recorded]
    assert "group.next_selected" in kinds and "group.turn_generated" in kinds
    assert all(message["content"] not in (data or "") for _, data in recorded)


def test_join_mode_and_scenario_override_via_api(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta", personality="Bold.", scenario="Card hall.")
    b = make_character(client, "Bryn", personality="Calm.", scenario="Card shore.")
    group = make_group(client, [a, b], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [b, a]}})
    put_deepening(client, gid, {
        "generation_mode": "join",
        "join_prefix": "<{{char}}>",
        "join_suffix": "</>",
        "scenario_override": "The group moot.",
    })
    result = next_turn(client, gid, user_text="Begin.", generate=True)
    assert result["speaker_id"] == b
    system = result["prompt"][0]["content"]
    assert "<Asta>" in system and "<Bryn>" in system
    assert "[Now speaking: Bryn]" in system
    assert "Card hall." not in system and "Card shore." not in system
    assert system.count("The group moot.") == 1


def test_persona_override_and_peek_do_not_mutate_card(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta", personality="Card-bold.")
    group = make_group(client, [a])
    gid = group["id"]
    peek0 = client.get(f"/api/v1/groups/{gid}/members/{a}/peek")
    assert peek0.status_code == 200
    assert peek0.json()["persona_source"] == "card"
    assert "Card-bold." in peek0.json()["effective_persona"]

    client.patch(
        f"/api/v1/groups/{gid}/members/{a}/override",
        json={"persona_override": "Room-only shadow persona."},
    )
    peek1 = client.get(f"/api/v1/groups/{gid}/members/{a}/peek").json()
    assert peek1["persona_source"] == "override"
    assert peek1["effective_persona"].startswith("Room-only shadow persona.")
    # The card itself is untouched: a fresh group sees the card persona.
    group2 = make_group(client, [a])
    peek2 = client.get(f"/api/v1/groups/{group2['id']}/members/{a}/peek").json()
    assert peek2["persona_source"] == "card"
    assert "Card-bold." in peek2["effective_persona"]
    assert client.get(f"/api/v1/groups/{gid}/members/nope/peek").status_code == 404


def test_group_lore_character_scope_and_lore_enabled(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = make_group(client, [a, b], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a, b]}})
    book = client.post("/api/v1/lorebooks", json={"name": "Asta Lore"})
    assert book.status_code == 201, book.text
    entry = client.post(
        f"/api/v1/lorebooks/{book.json()['id']}/entries",
        json={"name": "fact", "content": "Asta guards the old ford.",
              "keys": ["fact"], "constant": True},
    )
    assert entry.status_code == 201, entry.text
    scope = client.put(
        f"/api/v1/lorebooks/{book.json()['id']}/scope",
        json={"scope_kind": "character", "owner_id": a},
    )
    assert scope.status_code == 201, scope.text

    result = next_turn(client, gid, user_text="Tell me.", generate=True)
    assert result["speaker_id"] == a
    assert result["lore"] and result["lore"][0]["scope"] == "character"
    assert "Asta guards the old ford." in result["prompt"][0]["content"]

    client.patch(
        f"/api/v1/groups/{gid}/members/{a}/override", json={"lore_enabled": False}
    )
    again = next_turn(client, gid, generate=True)
    assert again["speaker_id"] == b  # list advanced to Bryn
    assert "Asta guards the old ford." not in again["prompt"][0]["content"]


def test_lore_disabled_for_speaker_drops_character_layer(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    group = make_group(client, [a], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a]}})
    book = client.post("/api/v1/lorebooks", json={"name": "Asta Lore"})
    bid = book.json()["id"]
    client.post(
        f"/api/v1/lorebooks/{bid}/entries",
        json={"name": "fact", "content": "Asta guards the old ford.",
              "keys": ["fact"], "constant": True},
    )
    client.put(
        f"/api/v1/lorebooks/{bid}/scope",
        json={"scope_kind": "character", "owner_id": a},
    )
    client.patch(
        f"/api/v1/groups/{gid}/members/{a}/override", json={"lore_enabled": False}
    )
    result = next_turn(client, gid, user_text="Tell me.", generate=True)
    assert result["speaker_id"] == a
    assert result["lore"] == []
    assert "Asta guards the old ford." not in result["prompt"][0]["content"]


# -- API: bounded run --------------------------------------------------------


def test_run_bounded_and_auto_cap(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    a = make_character(client, "Asta")
    b = make_character(client, "Bryn")
    group = make_group(client, [a, b], policy="list")
    gid = group["id"]
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a, b]}})
    put_deepening(client, gid, {"allow_self_responses": True})
    run = client.post(f"/api/v1/groups/{gid}/run", json={"turns": 3})
    assert run.status_code == 200, run.text
    assert run.json()["turns_run"] == 3
    assert [r["speaker_id"] for r in run.json()["results"]] == [a, b, a]

    put_deepening(client, gid, {
        "allow_self_responses": True,
        "auto_mode": {"enabled": True, "max_turns": 2},
    })
    capped = client.post(f"/api/v1/groups/{gid}/run", json={"turns": 5})
    assert capped.json()["cap"] == 2 and capped.json()["turns_run"] == 2

    bad = client.post(f"/api/v1/groups/{gid}/run", json={"turns": 11})
    assert bad.status_code == 422
    assert client.post("/api/v1/groups/nope/run", json={"turns": 1}).status_code == 404
    assert client.post("/api/v1/groups/nope/next", json={}).status_code == 404

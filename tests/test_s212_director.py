"""Roadmap S212 acceptance: pluggable director interface.

- The speaker-policy interface is a protocol; the S211 policies conform.
- A custom director registered at runtime becomes a valid group
  speaker-policy value through the API -- no group-service change.
- The deterministic fake LLM director (the seam) pins exact behavior:
  mention wins, least-recently-spoken next, mute is absolute, and the
  same room state always yields the same speaker.
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
from runmal.groupchat.policies import (
    DIRECTORS,
    MemberState,
    SelectionContext,
    SpeakerDirector,
    get_director,
    get_policy,
    register_director,
)

BRYN = MemberState("c-bryn", "Bryn", talkativeness=0.9)
UNA = MemberState("c-una", "Una", talkativeness=0.5)
KOL = MemberState("c-kol", "Kol", talkativeness=0.1)
ROSTER = [BRYN, UNA, KOL]

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


def ctx(**kwargs) -> SelectionContext:
    base = dict(members=list(ROSTER), seed=0)
    base.update(kwargs)
    return SelectionContext(**base)


def test_builtin_policies_conform_to_director_protocol() -> None:
    for name in ("manual", "natural", "list", "pooled", "fake-director"):
        director = get_director(name)
        assert isinstance(director, SpeakerDirector), name
        assert get_policy(name) is director  # one registry, two lookups


def test_fake_director_rotates_least_recent_first() -> None:
    director = get_director("fake-director")
    state = ctx()
    sequence = []
    for _ in range(4):
        picked = director.select(state)
        sequence.append(picked)
        director.note_selected(state, picked)
    # Nobody repeats until everyone has spoken; the chattiest opens
    # (never-spoken tie broken by talkativeness), then roster order
    # among the still-silent, then the cycle restarts by recency.
    assert sequence == ["c-bryn", "c-una", "c-kol", "c-bryn"]


def test_fake_director_mention_wins_and_mute_is_absolute() -> None:
    director = get_director("fake-director")
    state = ctx(last_user_text="@Kol, speak!", history_speakers=["c-bryn", "c-una"])
    assert director.select(state) == "c-kol"
    muted = ctx(
        members=[MemberState("c-kol", "Kol", muted=True), BRYN],
        last_user_text="@Kol, speak!",
    )
    assert director.select(muted) == "c-bryn"  # muted mention falls through
    nobody = ctx(members=[MemberState("c-a", "A", muted=True)])
    assert director.select(nobody) is None


def test_fake_director_is_fully_deterministic() -> None:
    director = get_director("fake-director")
    state = ctx(history_speakers=["c-una", "c-bryn", "c-una"])
    first = director.select(state)
    for _ in range(5):
        assert director.select(state) == first  # no RNG anywhere


def test_register_director_guards() -> None:
    class NoSelect:
        name = "broken"

    with pytest.raises(ValueError):
        register_director("broken", NoSelect())
    with pytest.raises(ValueError):
        register_director("natural", get_director("natural"))  # no shadowing
    with pytest.raises(ValueError):
        get_director("never-registered")


class LastSpeakerDirector:
    """Custom director used only by this test: the most recent speaker
    keeps the floor unless muted (then silence)."""

    name = "last-speaker"

    def select(self, ctx: SelectionContext) -> str | None:
        for speaker in reversed(ctx.history_speakers):
            member = ctx.member(speaker)
            if member is not None:
                return None if member.muted else member.character_id
        return None

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None:
        ctx.history_speakers.append(character_id)


def test_custom_director_selects() -> None:
    director = LastSpeakerDirector()
    state = ctx(history_speakers=["c-una"])
    assert director.select(state) == "c-una"
    assert director.select(ctx()) is None


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_custom_director_plugs_in_without_group_service_changes(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    group = client.post(
        "/api/v1/groups", json={"name": "Hall", "member_character_ids": [bryn]}
    ).json()

    # Before registration the name is not a valid policy value.
    early = client.patch(f"/api/v1/groups/{group['id']}", json={"speaker_policy": "last-speaker"})
    assert early.status_code == 422

    register_director("last-speaker", LastSpeakerDirector())
    try:
        updated = client.patch(
            f"/api/v1/groups/{group['id']}", json={"speaker_policy": "last-speaker"}
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["speaker_policy"] == "last-speaker"
        # The built-in fake director is equally valid out of the box.
        faked = client.patch(
            f"/api/v1/groups/{group['id']}", json={"speaker_policy": "fake-director"}
        )
        assert faked.status_code == 200
    finally:
        DIRECTORS.pop("last-speaker", None)
        from runmal.groupchat.policies import POLICIES

        POLICIES.pop("last-speaker", None)

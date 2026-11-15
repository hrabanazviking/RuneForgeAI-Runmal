"""R-11 acceptance (live): the group flow against the real
engine, in-process — a two-member room runs a turn per strategy
(the in-order strategy cycles the roster; manual honours the
chosen speaker), generation lands a reply in the transcript,
a "never" override removes a member from selection, and
leave/return + presence ride the real roads."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.group_logic import GroupFlow

CARD_A = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass.",
    "system_prompt": "You guard the pass.",
    "first_mes": "Well met.",
}
CARD_B = {
    "name": "Mask Bearer",
    "description": "Carries the old mask.",
    "personality": "Warm, quick, playful.",
    "scenario": "A mountain pass.",
    "system_prompt": "You carry the mask.",
    "first_mes": "Ho there.",
}


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> Iterator[EngineHandle]:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    try:
        yield handle
    finally:
        handle.stop()


def make_flow(engine: EngineHandle) -> tuple[GroupFlow, RunmalClient]:
    session = DesktopSession.from_local_credential(engine.base_url)
    client = RunmalClient(session)
    return GroupFlow(client), client


def build_room(flow: GroupFlow, client: RunmalClient):
    keeper = client.create_character(dict(CARD_A), name="Gate Keeper")
    bearer = client.create_character(dict(CARD_B), name="Mask Bearer")
    group = flow.create("Gate Watch", [keeper.id, bearer.id])
    return group, keeper, bearer


def test_turn_per_strategy(engine: EngineHandle) -> None:
    flow, client = make_flow(engine)
    group, keeper, bearer = build_room(flow, client)
    flow.say(group, "Who watches the gate tonight?")

    # In order: the roster cycles keeper -> bearer -> keeper.
    group = flow.set_policy(group, "list")
    first = flow.next_turn(group)
    second = flow.next_turn(group)
    assert first["speaker_id"] == keeper.id
    assert second["speaker_id"] == bearer.id

    # Manual: the chosen speaker is honoured exactly.
    group = flow.set_policy(group, "manual")
    picked = flow.next_turn(group, manual_speaker_id=bearer.id)
    assert picked["speaker_id"] == bearer.id

    # Natural + pooled at least name a roster member.
    for policy in ("natural", "pooled"):
        group = flow.set_policy(group, policy)
        result = flow.next_turn(group)
        assert result["speaker_id"] in (keeper.id, bearer.id)

    # Generation: the picked member's reply lands in the transcript.
    group = flow.set_policy(group, "list")
    before = len(flow.messages(group))
    result = flow.next_turn(group, generate=True)
    assert result["speaker_id"] in (keeper.id, bearer.id)
    messages = flow.messages(group)
    assert len(messages) > before
    assert messages[-1].speaker_id == result["speaker_id"]
    assert messages[-1].content.strip()


def test_override_presence_and_deepening(engine: EngineHandle) -> None:
    flow, client = make_flow(engine)
    group, keeper, bearer = build_room(flow, client)
    group = flow.set_policy(group, "list")

    # A "never" override removes the keeper from selection.
    flow.set_member_override(group, keeper.id, {"activation": "never"})
    result = flow.next_turn(group)
    assert result["speaker_id"] == bearer.id
    assert flow.member_override(group, keeper.id)["activation"] == "never"

    # Peek names the persona source honestly.
    peek = flow.peek(group, keeper.id)
    assert peek["persona_source"] == "card"
    flow.set_member_override(
        group, keeper.id, {"persona_override": "A sterner keeper."}
    )
    peek = flow.peek(group, keeper.id)
    assert peek["persona_source"] == "override"
    assert "sterner" in peek["effective_persona"]

    # Member settings + presence roads.
    group = flow.set_member(group, bearer.id, talkativeness=0.2, muted=True)
    member = next(m for m in group.members if m.character_id == bearer.id)
    assert member.talkativeness == 0.2 and member.muted is True
    flow.leave(group, bearer.id)
    records = flow.presence(group)
    assert len(records) == 2
    digest = flow.back(group, bearer.id)
    assert isinstance(digest, dict)

    # Deepening compose: the saved document keeps its state.
    deep = flow.deepening(group)
    deep["generation_mode"] = "join"
    saved = flow.save_deepening(group, deep)
    assert saved["generation_mode"] == "join"
    assert "state" in saved

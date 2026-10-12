"""Roadmap S211 acceptance: speaker policies — Manual/Natural/List/Pooled,
mute/talkativeness, seeded deterministic selection, fallback behavior.

Policy fixtures pin exact selections for fixed seeds. API tests cover the
persisted configuration: per-member talkativeness/muted and the group's
speaker-policy name + config.
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
    MemberState,
    SelectionContext,
    get_policy,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())

BRYN = MemberState("c-bryn", "Bryn", talkativeness=0.9)
UNA = MemberState("c-una", "Una", talkativeness=0.5)
KOL = MemberState("c-kol", "Kol", talkativeness=0.1)
ROSTER = [BRYN, UNA, KOL]


def ctx(**kwargs) -> SelectionContext:
    base = dict(members=list(ROSTER), seed=7)
    base.update(kwargs)
    return SelectionContext(**base)


# -- manual ---------------------------------------------------------------


def test_manual_designated_speaker() -> None:
    policy = get_policy("manual")
    assert policy.select(ctx(manual_speaker_id="c-una")) == "c-una"


def test_manual_fallbacks_are_silence() -> None:
    policy = get_policy("manual")
    assert policy.select(ctx()) is None  # nobody designated
    assert policy.select(ctx(manual_speaker_id="c-ghost")) is None  # unknown
    muted = ctx(
        members=[MemberState("c-una", "Una", muted=True)],
        manual_speaker_id="c-una",
    )
    assert policy.select(muted) is None  # muted designee: no substitution


# -- natural ---------------------------------------------------------------


def test_natural_mention_overrides_weights() -> None:
    policy = get_policy("natural")
    # Kol has the lowest talkativeness but is @-mentioned: he speaks.
    assert policy.select(ctx(last_user_text="@Kol, your craft?")) == "c-kol"
    # Mentioned-but-muted falls through to the weighted pick.
    members = [BRYN, UNA, MemberState("c-kol", "Kol", muted=True, talkativeness=0.1)]
    picked = policy.select(ctx(members=members, last_user_text="@Kol?"))
    assert picked in {"c-bryn", "c-una"}


def test_natural_seeded_weighted_pick_is_deterministic() -> None:
    policy = get_policy("natural")
    picks = [policy.select(ctx(seed=s)) for s in range(20)]
    again = [policy.select(ctx(seed=s)) for s in range(20)]
    assert picks == again  # same seed + state -> same speaker, every time
    # The high-talkativeness member dominates the seeded sequence.
    assert picks.count("c-bryn") > picks.count("c-kol")


def test_natural_zero_weights_fall_back_to_uniform() -> None:
    policy = get_policy("natural")
    members = [
        MemberState("c-a", "A", talkativeness=0.0),
        MemberState("c-b", "B", talkativeness=0.0),
    ]
    picks = {policy.select(ctx(members=members, seed=s)) for s in range(10)}
    assert picks == {"c-a", "c-b"}  # both reachable, deterministically per seed


def test_natural_all_muted_is_silence() -> None:
    policy = get_policy("natural")
    members = [MemberState("c-a", "A", muted=True), MemberState("c-b", "B", muted=True)]
    assert policy.select(ctx(members=members)) is None


# -- list -------------------------------------------------------------------


def test_list_cycles_and_skips() -> None:
    policy = get_policy("list")
    state = ctx(list_order=["c-kol", "c-bryn", "c-una"])
    sequence = []
    for _ in range(4):
        picked = policy.select(state)
        sequence.append(picked)
        policy.note_selected(state, picked)
    assert sequence == ["c-kol", "c-bryn", "c-una", "c-kol"]  # wraps around

    # Muted and departed ids drop out of the effective order.
    state = ctx(
        members=[BRYN, MemberState("c-una", "Una", muted=True)],
        list_order=["c-una", "c-gone", "c-bryn"],
    )
    assert policy.select(state) == "c-bryn"


def test_list_empty_order_is_silence() -> None:
    policy = get_policy("list")
    assert policy.select(ctx(list_order=[])) is None
    assert policy.select(ctx(list_order=["c-gone"])) is None


# -- pooled -----------------------------------------------------------------


def test_pooled_no_repeats_until_pool_resets() -> None:
    policy = get_policy("pooled")
    state = ctx(seed=3)
    spoken = []
    for turn in range(3):
        state.seed = 3 + turn
        picked = policy.select(state)
        assert picked not in spoken  # pool excludes prior speakers
        spoken.append(picked)
        policy.note_selected(state, picked)
    assert sorted(spoken) == ["c-bryn", "c-kol", "c-una"]
    # Pool exhausted -> reset: a fourth pick is possible again.
    state.seed = 99
    assert policy.select(state) in {"c-bryn", "c-kol", "c-una"}


def test_pooled_deterministic_and_mute_safe() -> None:
    policy = get_policy("pooled")
    a = policy.select(ctx(seed=42))
    b = policy.select(ctx(seed=42))
    assert a == b
    members = [MemberState("c-a", "A", muted=True), MemberState("c-b", "B")]
    assert policy.select(ctx(members=members, seed=1)) == "c-b"
    all_muted = [MemberState("c-a", "A", muted=True)]
    assert policy.select(ctx(members=all_muted)) is None


def test_unknown_policy_rejected() -> None:
    with pytest.raises(ValueError):
        get_policy("chaos")
    with pytest.raises(ValueError):
        MemberState("c-x", "X", talkativeness=1.5)


# -- persisted configuration (API) ------------------------------------------


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


def test_group_policy_config_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    group = client.post(
        "/api/v1/groups", json={"name": "Hall", "member_character_ids": [bryn]}
    ).json()
    assert group["speaker_policy"] == "natural"  # documented default
    assert group["speaker_config"] == {}

    updated = client.patch(
        f"/api/v1/groups/{group['id']}",
        json={"speaker_policy": "list", "speaker_config": {"order": [bryn]}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["speaker_policy"] == "list"
    assert updated.json()["speaker_config"] == {"order": [bryn]}

    bad = client.patch(f"/api/v1/groups/{group['id']}", json={"speaker_policy": "chaos"})
    assert bad.status_code == 422


def test_member_settings_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    group = client.post(
        "/api/v1/groups", json={"name": "Hall", "member_character_ids": [bryn]}
    ).json()
    member = group["members"][0]
    assert member["talkativeness"] == 0.5 and member["muted"] is False

    updated = client.patch(
        f"/api/v1/groups/{group['id']}/members/{bryn}",
        json={"talkativeness": 0.25, "muted": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["talkativeness"] == 0.25
    assert updated.json()["muted"] is True

    bad = client.patch(
        f"/api/v1/groups/{group['id']}/members/{bryn}",
        json={"talkativeness": 1.5},
    )
    assert bad.status_code == 422
    missing = client.patch(f"/api/v1/groups/{group['id']}/members/nope", json={"muted": True})
    assert missing.status_code == 404

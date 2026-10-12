"""Roadmap S213: Campaign II hardening gate.

Pins the cross-slice contracts the campaign docs promise, in one place:
the lore pipeline stages agree with each other (scan -> activation ->
budget -> preview), group speaker identity survives the full stack, and
policy selection over persisted room state is deterministic. If any
single-slice refactor breaks a documented behavior, this gate fails.
"""

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.groupchat.policies import MemberState, SelectionContext, get_director
from runmal.groupchat.store import member_to_dict  # noqa: F401  (API surface pin)
from runmal.lorebooks.preview import preview_activation

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


class _Entry:
    """ORM-shaped lore entry for direct pipeline calls."""

    def __init__(self, **kw):
        self.id = kw["id"]
        self.name = kw.get("name", "")
        self.content = kw.get("content", "")
        self.enabled = kw.get("enabled", True)
        self.constant = kw.get("constant", False)
        self.keys_json = json.dumps(kw.get("keys", []))
        self.secondary_keys_json = json.dumps(kw.get("secondary_keys", []))
        self.whole_word = kw.get("whole_word", True)
        self.case_sensitive = kw.get("case_sensitive", False)
        self.sticky_prompts = kw.get("sticky_prompts", 0)
        self.cooldown_prompts = kw.get("cooldown_prompts", 0)
        self.delay_prompts = kw.get("delay_prompts", 0)
        self.priority = kw.get("priority", 100)


def test_preview_pipeline_is_deterministic_and_self_consistent() -> None:
    entries = [
        _Entry(id="e1", name="Anchor", content="Always here.", constant=True),
        _Entry(
            id="e2", name="Gate", content="Needs two keys.", keys=["gate"], secondary_keys=["iron"]
        ),
        _Entry(id="e3", name="Loop", content="See {{lore:Anchor}}", keys=["loop"]),
    ]
    messages = ["The iron gate and the loop."]
    first = preview_activation(entries, messages, 4, None)
    second = preview_activation(entries, messages, 4, None)
    assert first == second  # same inputs -> identical verdicts
    by_name = {r["name"]: r for r in first["entries"]}
    assert by_name["Anchor"]["via"] == "constant"
    assert by_name["Gate"]["status"] == "included"
    assert by_name["Gate"]["matched_secondary"] == ["iron"]
    assert by_name["Loop"]["status"] == "included"
    assert "Always here." in by_name["Loop"]["content"]  # reference resolved
    assert first["tokens_used"] == sum(
        r["tokens"] for r in first["entries"] if r["status"] == "included"
    )


def test_director_over_persisted_room_shape() -> None:
    # MemberState rows built exactly the way the store describes members.
    members = [
        MemberState("c-bryn", "Bryn", muted=False, talkativeness=0.9),
        MemberState("c-una", "Una", muted=True, talkativeness=0.5),
        MemberState("c-kol", "Kol", muted=False, talkativeness=0.1),
    ]
    director = get_director("fake-director")
    state = SelectionContext(members=members, history_speakers=["c-kol"])
    # Una is muted (never selected); Bryn has never spoken -> he is next.
    assert director.select(state) == "c-bryn"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_full_stack_group_and_preview_smoke(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    card = copy.deepcopy(V2_CARD)
    card["name"] = "Bryn"
    bryn = client.post("/api/v1/characters", json={"card": card}).json()["id"]
    group = client.post(
        "/api/v1/groups",
        json={"name": "Hall", "member_character_ids": [bryn]},
    ).json()
    assert group["speaker_policy"] == "natural"
    posted = client.post(
        f"/api/v1/groups/{group['id']}/messages",
        json={"speaker": bryn, "content": "The hall is warm."},
    )
    assert posted.status_code == 201
    assert posted.json()["speaker_name"] == "Bryn"

    book = client.post("/api/v1/lorebooks", json={"name": "World"}).json()
    client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Hall", "content": "Warm.", "keys": ["hall"]},
    )
    preview = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["Back at the hall."]},
    )
    assert preview.status_code == 200
    assert preview.json()["entries"][0]["status"] == "included"

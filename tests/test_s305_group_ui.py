"""S305 acceptance: group chat UI scenario tests.

Roster from real characters, strategy picker semantics over SSE
(typing -> token -> message per participant), per-author attribution,
round-robin cursor carry, and page wiring.
"""

import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_characters(client):
    ids = {}
    for name in ("Bryn", "Una", "Kol"):
        resp = client.post(
            "/api/v1/characters",
            json={"card": {"name": name, "personality": f"{name} persona."}},
        )
        assert resp.status_code == 201, resp.text
        ids[name] = resp.json()["id"]
    return ids


def run_turn(client, ids, user_text, strategy="mention", history=None, cursor=0):
    with client.stream(
        "POST",
        "/api/v1/group/turn",
        json={
            "participant_ids": ids,
            "history": history or [],
            "user_text": user_text,
            "strategy": strategy,
            "rr_cursor": cursor,
        },
    ) as resp:
        assert resp.status_code == 200, resp.status
        raw = "".join(resp.iter_text())
    events = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def test_mention_scenario_streams_one_speaker(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    ids = make_characters(client)
    events = run_turn(client, list(ids.values()), "Hey @Una, your counsel?")
    types = [(e["type"], e.get("author")) for e in events]
    assert ("typing", "Una") in types
    assert ("message", "Una") in types
    assert not any(a == "Bryn" for _, a in types)
    assert not any(a == "Kol" for _, a in types)
    # order: typing before first token before message
    seq = [t for t, _ in types]
    assert seq.index("typing") < seq.index("token") < seq.index("message")
    assert events[-1]["type"] == "turn_end"
    msg = next(e for e in events if e["type"] == "message")
    assert msg["content"]  # the fake backend said something


def test_broadcast_scenario_all_speak_in_order(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    ids = make_characters(client)
    events = run_turn(client, list(ids.values()), "Speak, all.",
                      strategy="broadcast")
    speakers = [e["author"] for e in events if e["type"] == "message"]
    assert speakers == ["Bryn", "Una", "Kol"]


def test_round_robin_cursor_carries(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    ids = make_characters(client)
    history = []
    cursor = 0
    speakers = []
    for i in range(4):
        events = run_turn(client, list(ids.values()), f"q{i}",
                          strategy="round_robin", history=history,
                          cursor=cursor)
        msg = next(e for e in events if e["type"] == "message")
        speakers.append(msg["author"])
        cursor = events[-1]["rr_cursor"]
        history.append({"author": "user", "content": f"q{i}"})
        history.append({"author": msg["author"], "content": msg["content"]})
    assert speakers == ["Bryn", "Una", "Kol", "Bryn"]


def test_unknown_participant_and_strategy_rejected(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    ids = make_characters(client)
    resp = client.post(
        "/api/v1/group/turn",
        json={"participant_ids": ["ghost"], "user_text": "hi"},
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/v1/group/turn",
        json={"participant_ids": list(ids.values()), "user_text": "hi",
              "strategy": "chaos"},
    )
    assert resp.status_code == 422


def test_group_ui_page(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/group")
    assert page.status_code == 200
    for marker in ('id="roster"', 'id="strategy"', 'id="group-thread"',
                   'id="group-input"', "group.js"):
        assert marker in page.text, marker
    js = client.get("/static/group.js")
    assert js.status_code == 200
    assert "/api/v1/group/turn" in js.text
    assert "typing" in js.text

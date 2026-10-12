"""S213 acceptance: impersonation/depth tools integration tests.

Controls over S206 (depth injection) and S209 (session state machine):
compose preview splices the note at the requested depth, impossible prompt
states return visible 422s, the session driver walks the full lifecycle
(including impersonate commit-as-user), and the /tools UI is wired.
"""

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


def act(client, session, action, **kw):
    resp = client.post(
        "/api/v1/tools/session", json={"action": action, "session": session, **kw}
    )
    return resp


def test_compose_preview_depth_injection(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    history = [f"turn-{i} " + "x" * 30 for i in range(4)]
    resp = client.post(
        "/api/v1/tools/compose",
        json={
            "system": "You are Yrsa.",
            "history": history,
            "authors_note": "Remember the oath.",
            "note_depth": 1,
            "context_limit": 4096,
            "reserve_response": 100,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    slot_ids = [m["slot_id"] for m in body["messages"]]
    assert slot_ids == ["system", "history", "note", "history"]
    assert body["manifest"]["total_input_tokens"] <= body["manifest"]["input_budget"]


def test_compose_impossible_state_is_visible_422(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/tools/compose",
        json={
            "system": "S" * 4000,  # required slot bigger than the allowance
            "context_limit": 100,
            "reserve_response": 50,
        },
    )
    assert resp.status_code == 422
    assert "required" in resp.json()["detail"]


def test_session_lifecycle_and_swipe(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    msgs = [{"role": "user", "content": "Tell me of the sea."}]
    out = act(client, None, "create", mode="normal").json()
    session = out["session"]
    out = act(client, session, "compose", messages=msgs).json()
    assert out["result"]["fingerprint"]
    session = out["session"]
    session = act(client, session, "begin").json()["session"]
    out = act(client, session, "complete", content="v1").json()
    session = out["session"]
    session = act(client, session, "regenerate", messages=msgs).json()["session"]
    session = act(client, session, "begin").json()["session"]
    session = act(client, session, "complete", content="v2").json()["session"]
    out = act(client, session, "swipe", delta=-1).json()
    assert out["result"]["active"]["content"] == "v1"  # candidates persisted
    out = act(client, out["session"], "commit").json()
    assert out["result"]["role"] == "assistant"
    assert out["result"]["content"] == "v1"


def test_session_impersonate_commits_as_user(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    msgs = [{"role": "user", "content": "Begin."}]
    session = act(client, None, "create", mode="impersonate").json()["session"]
    session = act(client, session, "compose", messages=msgs).json()["session"]
    session = act(client, session, "begin").json()["session"]
    session = act(client, session, "complete", content="I draw my sword.").json()["session"]
    out = act(client, session, "commit").json()
    assert out["result"]["role"] == "user"
    assert out["result"]["content"] == "I draw my sword."


def test_session_errors_are_visible(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    session = act(client, None, "create", mode="normal").json()["session"]
    # begin before compose: invalid transition, readable 422
    bad = act(client, session, "begin")
    assert bad.status_code == 422
    assert "cannot begin" in bad.json()["detail"]
    # regenerate with a changed prompt: prompt-identity error, readable 422
    msgs = [{"role": "user", "content": "one"}]
    session = act(client, session, "compose", messages=msgs).json()["session"]
    session = act(client, session, "begin").json()["session"]
    session = act(client, session, "complete", content="v1").json()["session"]
    changed = act(client, session, "regenerate",
                  messages=[{"role": "user", "content": "two"}])
    assert changed.status_code == 422
    assert "identical prompt" in changed.json()["detail"]
    # unknown action
    weird = act(client, session, "explode")
    assert weird.status_code == 422


def test_tools_ui_page(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/tools")
    assert page.status_code == 200
    for marker in ('id="compose-panel"', 'id="session-panel"', 'id="c-depth"',
                   'id="s-mode"', 'id="error-banner"', "tools.js"):
        assert marker in page.text, marker
    js = client.get("/static/tools.js")
    assert js.status_code == 200
    assert "/api/v1/tools/compose" in js.text
    assert "/api/v1/tools/session" in js.text

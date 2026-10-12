"""S109 acceptance (HTTP level): chat page serves, static assets, no secret leak."""

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
    return TestClient(create_app(create_session_factory(engine)))


def test_chat_page_public_and_has_markers(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    for marker in (
        "<title>Rúnmál — chat</title>",
        "/static/app.js",
        "/static/style.css",
        'id="token-gate"',
        'id="thread"',
        'id="send"',
        'id="stop"',
        'id="error-banner"',
        "local_credential",  # credential *path* hint only
    ):
        assert marker in body, marker


def test_chat_page_does_not_leak_secret(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = get_or_create_credential()
    assert token not in client.get("/chat").text
    assert token not in client.get("/static/app.js").text


def test_index_redirects_to_chat(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert resp.headers["location"].endswith("/chat")


def test_static_assets_served(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "crypto.randomUUID" in js.text  # client-generated request ids
    assert "/api/v1/generate/cancel" in js.text  # Stop button wiring
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "#token-gate" in css.text

"""S211 acceptance: connection profiles API/UI + health with a fake probe.

List/detail, set-active (single-active invariant), health probe reporting
latency and capabilities, and the /connections UI page.
"""

import time

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.connections.service import ProbeOutcome, probe_profile
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import ConnectionProfile


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_crud_and_first_profile_auto_activates(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/connections",
        json={"name": "local-fake", "backend": "fake"},
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["is_active"] is True

    second = client.post(
        "/api/v1/connections",
        json={"name": "laptop-ollama", "backend": "ollama",
              "base_url": "http://localhost:11434", "model": "llama3"},
    ).json()
    assert second["is_active"] is False

    listed = client.get("/api/v1/connections").json()
    assert [p["name"] for p in listed] == ["laptop-ollama", "local-fake"]
    detail = client.get(f"/api/v1/connections/{second['id']}").json()
    assert detail["model"] == "llama3"

    assert client.delete(f"/api/v1/connections/{second['id']}").status_code == 200
    assert client.get(f"/api/v1/connections/{second['id']}").status_code == 404


def test_set_active_keeps_single_active(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    a = client.post("/api/v1/connections", json={"name": "a"}).json()
    b = client.post("/api/v1/connections", json={"name": "b"}).json()
    resp = client.post(f"/api/v1/connections/{b['id']}/activate")
    assert resp.status_code == 200
    listed = client.get("/api/v1/connections").json()
    actives = [p["name"] for p in listed if p["is_active"]]
    assert actives == ["b"]
    assert (
        client.post("/api/v1/connections/nope/activate").status_code == 404
    )
    assert a["id"] != b["id"]


def test_invalid_backend_and_duplicate_name(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    bad = client.post(
        "/api/v1/connections", json={"name": "x", "backend": "carrier-pigeon"}
    )
    assert bad.status_code == 422
    client.post("/api/v1/connections", json={"name": "dup"})
    dup = client.post("/api/v1/connections", json={"name": "dup"})
    assert dup.status_code == 409


def test_health_with_fake_probe(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    profile = client.post(
        "/api/v1/connections", json={"name": "probe-me", "backend": "ollama"}
    ).json()

    def fake_prober(p):
        time.sleep(0.01)
        return ProbeOutcome(True, ["streaming", "local-models"], "fake probe ok")

    client.app.state.prober = fake_prober
    resp = client.get(f"/api/v1/connections/{profile['id']}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["latency_ms"] >= 9  # the fake probe slept ~10ms
    assert body["capabilities"] == ["streaming", "local-models"]
    assert body["detail"] == "fake probe ok"

    def failing_prober(p):
        return ProbeOutcome(False, [], "connection refused (fake)")

    client.app.state.prober = failing_prober
    body = client.get(f"/api/v1/connections/{profile['id']}/health").json()
    assert body["ok"] is False
    assert body["capabilities"] == []
    assert body["latency_ms"] >= 0


def test_health_default_probe_fake_backend(tmp_path, monkeypatch) -> None:
    profile = ConnectionProfile(
        id="p1", user_id="u1", name="f", backend="fake"
    )
    result = probe_profile(profile)
    assert result.ok is True
    assert "streaming" in result.capabilities
    assert result.latency_ms >= 0


def test_connections_ui_page(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/connections")
    assert page.status_code == 200
    assert 'id="connection-list"' in page.text
    assert 'id="create-form"' in page.text
    assert "connections.js" in page.text
    js = client.get("/static/connections.js")
    assert js.status_code == 200
    assert "/api/v1/connections" in js.text

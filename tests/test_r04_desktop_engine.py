"""R-04 acceptance (engine lifecycle + live client): the in-process
engine starts, reads REAL /healthz state through its status
transitions, stops cleanly — and the typed client + first-run
detection work against that live engine on a fresh data dir.

No Qt here either: the lifecycle module is Qt-free by design.
"""

import httpx
import pytest

from runmal.auth import get_or_create_credential
from runmal.desktop.client import (
    DesktopSession,
    RunmalClient,
    TransportError,
    fetch_snapshot,
)
from runmal.desktop.engine import EngineHandle, EngineState

CARD = {
    "name": "Proof Companion",
    "description": "Stands at the R-04 proof gate.",
    "personality": "Calm.",
    "scenario": "A test hall.",
    "first_mes": "Well met.",
    "system_prompt": "You are the Proof Companion.",
}


@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    yield handle
    handle.stop()


def test_engine_lifecycle_status_transitions(live_engine) -> None:
    handle = live_engine
    assert handle.status().state is EngineState.STOPPED
    assert handle.is_running is False

    started = handle.start(timeout=30.0)
    assert started.state is EngineState.RUNNING
    assert "running" in started.label
    assert handle.is_running is True
    # Real /healthz, read independently of the handle's own claim.
    with httpx.Client(trust_env=False, timeout=5.0) as http:
        resp = http.get(f"{handle.base_url}/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Starting twice is a no-op status read, not a second server.
    assert handle.start(timeout=5.0).state is EngineState.RUNNING

    stopped = handle.stop()
    assert stopped.state is EngineState.STOPPED
    assert handle.is_running is False
    assert handle.stop().state is EngineState.STOPPED  # idempotent


def test_client_against_live_engine_and_first_run(live_engine) -> None:
    handle = live_engine
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    client = RunmalClient(
        DesktopSession.from_local_credential(handle.base_url)
    )
    try:
        health = client.health()
        assert health.ok is True
        assert client.api_status()["auth"] == "local"

        # Fresh data dir: the §1.3.4 empty state — first run.
        fresh = client.first_run_state()
        assert fresh.is_first_run is True
        assert fresh.profile_count == 0 and fresh.character_count == 0

        # Configure one profile + one character through the real API.
        token = get_or_create_credential()
        with httpx.Client(
            base_url=handle.base_url, trust_env=False, timeout=10.0,
            headers={"Authorization": f"Bearer {token}"},
        ) as http:
            created = http.post(
                "/api/v1/backend-profiles",
                json={"name": "hearth", "chat_backend": "fake",
                      "chat_model": "fake-1"},
            )
            assert created.status_code == 201, created.text
            profile_id = created.json()["id"]
            made = http.post("/api/v1/characters", json={"card": CARD})
            assert made.status_code in (200, 201), made.text

        after = client.first_run_state()
        assert after.is_first_run is False
        assert after.profile_count == 1 and after.character_count == 1

        snapshot = fetch_snapshot(client)
        assert snapshot.profiles[0].id == profile_id
        assert snapshot.characters[0].name == "Proof Companion"
        assert client.profile_health(profile_id)["ok"] is True
        assert client.profile_models(profile_id)[0]["model_id"] == "fake-1"
    finally:
        client.close()

    handle.stop()
    with pytest.raises(TransportError):
        RunmalClient(
            DesktopSession(handle.base_url, bearer_token="x")
        ).health()

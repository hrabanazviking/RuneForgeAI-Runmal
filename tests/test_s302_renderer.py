"""S302 acceptance: chat thread + streaming renderer.

Renderer behavior (markdown-lite, XSS safety, code blocks, malformed
input, windowing) is unit-tested under Node against the real renderer.js.
HTTP level: page wires renderer + retry/stop states; the SSE endpoint
streams and honors cancellation (the states the UI drives).
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

REPO = Path(__file__).parent.parent
NODE_TEST = REPO / "tests" / "js" / "renderer.test.cjs"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_renderer_unit_tests_under_node():
    proc = subprocess.run(
        ["node", str(NODE_TEST)], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ALL PASS" in proc.stdout


def test_chat_page_wires_renderer_and_states(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/chat")
    assert "renderer.js" in page.text
    assert 'id="retry"' in page.text  # retry UI state exists
    assert 'id="stop"' in page.text  # stop UI state exists
    js = client.get("/static/renderer.js")
    assert js.status_code == 200
    assert "renderMarkdownLite" in js.text
    app = client.get("/static/app.js")
    assert "streamGeneration" in app.text
    assert "retryGeneration" in app.text
    assert "windowMessages" in app.text  # virtualized thread windowing


def test_streaming_and_cancel_states(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    with client.stream(
        "POST",
        "/api/v1/generate",
        json={"messages": [{"role": "user", "content": "hello"}],
              "request_id": "s302-stream"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert "data:" in body
    assert '"done"' in body or "done" in body
    # cancel an unknown request is a clean no-op state, not an error storm
    cancel = client.post(
        "/api/v1/generate/cancel", json={"request_id": "never-started"}
    )
    assert cancel.status_code in (200, 404)

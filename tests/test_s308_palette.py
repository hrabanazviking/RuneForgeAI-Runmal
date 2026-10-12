"""S308 acceptance: command palette + keyboard map.

The registry is validated under Node (every action reachable, ids
stable, no shortcut conflicts, fuzzy ranking). HTTP level: the palette
overlay + script are wired into every page.
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
NODE_TEST = REPO / "tests" / "js" / "palette.test.cjs"
PAGES = ("/chat", "/gallery", "/lorebooks", "/editor", "/connections",
         "/tools", "/group")


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
def test_palette_registry_under_node():
    proc = subprocess.run(
        ["node", str(NODE_TEST)], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ALL PASS" in proc.stdout


def test_palette_wired_into_every_page(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    for page in PAGES:
        body = client.get(page)
        assert body.status_code == 200, page
        assert 'id="palette"' in body.text, page
        assert 'id="palette-input"' in body.text, page
        assert "palette.js" in body.text, page
    js = client.get("/static/palette.js")
    assert js.status_code == 200
    assert "ctrlKey" in js.text or "metaKey" in js.text  # mod+K opens it

"""S311 acceptance: UI regression + visual fixtures (Campaign III gate).

Golden structural fixtures for every screen: the signature of each
rendered page (ids, landmarks, roles, scripts) is pinned under
tests/fixtures/ui/. A mismatch fails loudly with a unified diff.
Regenerate deliberately with RUNMAL_UPDATE_GOLDENS=1.

The campaign regression gate is this module plus the full suite in one
command:  pytest tests/
"""

import difflib
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

FIXTURES = Path(__file__).parent / "fixtures" / "ui"
PAGES = {
    "chat": "/chat",
    "connections": "/connections",
    "editor": "/editor",
    "gallery": "/gallery",
    "group": "/group",
    "inspector": "/inspector",
    "lorebooks": "/lorebooks",
    "tools": "/tools",
}
LANDMARKS = {"main", "nav", "aside", "header", "footer"}


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


class SignatureParser(HTMLParser):
    """Collects the structural signature: ids, landmarks, roles, assets."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.lines.add(f"{tag}#{a['id']}")
        if tag in LANDMARKS:
            self.lines.add(f"landmark:{tag}")
        if "role" in a:
            self.lines.add(f"{tag}[role={a['role']}]")
        if tag == "script" and a.get("src"):
            self.lines.add(f"script:{a['src']}")
        if tag == "link" and a.get("href"):
            self.lines.add(f"link:{a['href']}")
        if tag == "html":
            self.lines.add(f"html[lang={a.get('lang')}]")


def signature(html: str) -> str:
    parser = SignatureParser()
    parser.feed(html)
    return "\n".join(sorted(parser.lines)) + "\n"


def test_golden_fixtures(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    update = os.environ.get("RUNMAL_UPDATE_GOLDENS") == "1"
    failures = []
    for name, route in PAGES.items():
        golden_path = FIXTURES / f"{name}.golden.txt"
        actual = signature(client.get(route).text)
        if update:
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(actual, encoding="utf-8")
            continue
        assert golden_path.exists(), (
            f"missing golden fixture for {name}: {golden_path} "
            "(run with RUNMAL_UPDATE_GOLDENS=1 to create it deliberately)"
        )
        expected = golden_path.read_text(encoding="utf-8")
        if actual != expected:
            diff = "\n".join(
                difflib.unified_diff(
                    expected.splitlines(), actual.splitlines(),
                    fromfile=f"golden/{name}", tofile=f"rendered/{name}",
                    lineterm="",
                )
            )
            failures.append(f"--- {name} structural mismatch ---\n{diff}")
    assert not failures, "\n\n".join(failures)


# -- Campaign II + III feature gate -----------------------------------------

FEATURES = [
    # (feature, route, marker that must be present)
    ("S302 streaming renderer", "/static/app.js", "streamGeneration"),
    ("S302 markdown renderer", "/static/renderer.js", "renderMarkdown"),
    ("S302 retry on failure", "/chat", 'id="retry"'),
    ("S303 gallery search", "/gallery", 'id="search"'),
    ("S303 import dropzone", "/gallery", 'id="dropzone"'),
    ("S304 lorebook import", "/lorebooks", 'id="import-file"'),
    ("S304 entry editor", "/lorebooks", 'id="entry-form"'),
    ("S305 group page", "/group", 'id="group-form"'),
    ("S306 model picker", "/connections", 'id="health-models"'),
    ("S306 preset picker", "/chat", 'id="preset-select"'),
    ("S307 variable chips", "/tools", 'id="variable-chips"'),
    ("S308 command palette", "/chat", 'id="palette"'),
    ("S309 live region", "/chat", 'id="sr-status"'),
    ("S309 skip link", "/tools", 'class="skip-link"'),
    ("S310 drawer toggle", "/chat", 'id="sidebar-toggle"'),
    ("S310 drawer script", "/chat", "drawer.js"),
    ("S211 connections page", "/connections", 'id="create-form"'),
    ("S212 persona editor", "/editor", 'id="editor-form"'),
    ("S213 tools page", "/tools", 'id="compose-panel"'),
]


def test_campaign_feature_gate(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    missing = []
    for feature, route, marker in FEATURES:
        body = client.get(route)
        if body.status_code != 200 or marker not in body.text:
            missing.append(f"{feature}: {marker!r} not found at {route}")
    assert not missing, "Campaign II+III feature regressions:\n" + "\n".join(missing)


def test_all_pages_share_chrome(tmp_path, monkeypatch) -> None:
    """Every page loads the token stylesheet + palette (shared chrome)."""
    client = make_client(tmp_path, monkeypatch)
    for name, route in PAGES.items():
        body = client.get(route).text
        assert "/static/style.css" in body, name
        assert 'id="palette"' in body, name
        assert "palette.js" in body, name

"""R-16 standing gate: the web shell is gone and cannot rot back.

The desktop shell covers everything the web shell ever did, so the
web package, its page routes, and the browser/Tk launcher roads are
scrapped. This gate stands permanently (§1.6 lesson — a front end
must never rot silently again):

(a) ``runmal.web`` is not importable and its source tree is absent;
(b) the built app serves NO old page path, while the API answers;
(c) every shipped desktop front-end file parses, and importing the
    desktop client layer pulls in no PySide6 (the R-04 pattern);
(d) the launcher's open road targets the desktop module, with the
    actual spawn stubbed through the launcher's runner seam.

W-01 amendment (ADR-0012, Volmarr's order 2026-11-27): the NEW
web face lives in its own package, ``runmal.webface`` — a
separate process over the same HTTP API. The old ``runmal.web``
package stays buried exactly as this gate asserts; the
sanctioned ``runmal.webface`` package is not a violation.
"""

from __future__ import annotations

import importlib.util
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.launcher import core as launcher_core

REPO = Path(__file__).parent.parent
SRC = REPO / "src"
DESKTOP = SRC / "runmal" / "desktop"

OLD_PAGE_PATHS = (
    "/",
    "/chat",
    "/connections",
    "/editor",
    "/tools",
    "/gallery",
    "/lorebooks",
    "/group",
    "/inspector",
    "/voice",
    "/memories",
)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# -- (a) the web package is gone --------------------------------------------


def test_web_package_not_importable_and_tree_absent():
    assert importlib.util.find_spec("runmal.web") is None
    assert not (SRC / "runmal" / "web").exists()
    # ADR-0012: the sanctioned web face is a DIFFERENT package
    # (runmal.webface, a separate process); its presence is the
    # W-01 order, not the buried shell rotting back.
    assert (SRC / "runmal" / "webface").is_dir()
    with pytest.raises(ModuleNotFoundError):
        __import__("runmal.web")


def test_launcher_gui_tk_control_center_absent():
    assert importlib.util.find_spec("runmal.launcher.gui") is None
    assert not (SRC / "runmal" / "launcher" / "gui.py").exists()


# -- (b) the app serves no pages, the API answers ----------------------------


def test_app_serves_no_old_page_paths(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    for path in OLD_PAGE_PATHS:
        response = client.get(path)
        assert response.status_code == 404, (path, response.status_code)
        assert "text/html" not in response.headers.get("content-type", ""), path
    # The static mount is gone too.
    assert client.get("/static/app.js").status_code == 404
    # No page path is hiding in the OpenAPI census either.
    paths = client.get("/openapi.json").json()["paths"]
    for path in OLD_PAGE_PATHS:
        assert path not in paths, path
    assert "/api/v1/memories-browser" not in paths


def test_api_road_still_answers(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    status = client.get("/api/v1/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ok"
    assert client.get("/healthz").status_code == 200


# -- (c) the desktop front end parses and stays Qt-free at the client layer --


def test_every_desktop_file_parses():
    files = sorted(DESKTOP.rglob("*.py"))
    assert files, "desktop front end must exist"
    for path in files:
        py_compile.compile(str(path), doraise=True)


def test_desktop_client_import_pulls_in_no_qt():
    code = (
        "import sys\n"
        "import runmal.desktop.client\n"
        "assert 'PySide6' not in sys.modules, 'client layer pulled in Qt'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr


# -- (d) the launcher open road targets the desktop module -------------------


def test_launcher_open_road_spawns_desktop_module(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    spawned: list[list[str]] = []

    def fake_spawn(command, **kwargs):
        spawned.append(command)
        return object()

    command = launcher_core.open_runmal(runner=fake_spawn)
    assert command == [sys.executable, "-m", "runmal.desktop"]
    assert spawned == [command]


def test_launcher_parser_has_no_browser_or_control_roads():
    from runmal.launcher.__main__ import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["control"])
    args = parser.parse_args(["open", "--no-launch"])
    assert args.command == "open"
    assert args.no_launch is True

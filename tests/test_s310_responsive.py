"""S310 acceptance: mobile/responsive pass.

CSS level: breakpoints exist and the phone layout cannot overflow
horizontally (single column, drawer off-canvas, fluid widths); touch
targets and safe-area insets are in the stylesheet. Drawer behavior is
unit-tested under Node; wiring is asserted at HTTP level.
"""

import re
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
CSS = (REPO / "src" / "runmal" / "web" / "static" / "style.css").read_text(
    encoding="utf-8"
)
NODE_TEST = REPO / "tests" / "js" / "drawer.test.cjs"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def media_block(query: str) -> str:
    start = CSS.index(query)
    return CSS[start:start + 1600]


def test_breakpoints_present():
    assert "@media (max-width: 1024px)" in CSS
    assert "@media (max-width: 720px)" in CSS
    assert "@media (pointer: coarse)" in CSS


def test_phone_layout_no_horizontal_overflow():
    block = media_block("@media (max-width: 720px)")
    # drawer off-canvas until .open
    assert "transform: translateX(-105%)" in block
    assert "#sidebar.open" in block and "transform: none" in block
    # single-column group layout + fluid gallery cells + capped bubbles
    assert ".group-layout { grid-template-columns: 1fr; }" in block
    assert "minmax(150px, 1fr)" in block
    assert ".msg { max-width: 92%; }" in block
    # the sidebar itself is fluid-capped, never wider than the viewport
    assert "min(300px, 85vw)" in block


def test_touch_targets_and_safe_areas():
    coarse = media_block("@media (pointer: coarse)")
    assert "min-height: var(--touch-target)" in coarse
    assert "--touch-target: 44px" in CSS
    assert "env(safe-area-inset-bottom)" in CSS


def test_no_fixed_pixel_widths_wider_than_phone():
    """No component sets a fixed width above the phone breakpoint."""
    for m in re.finditer(r"(?<![-\w])width:\s*(\d+)px", CSS):
        assert int(m.group(1)) <= 720, m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_drawer_state_machine_under_node():
    proc = subprocess.run(
        ["node", str(NODE_TEST)], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ALL PASS" in proc.stdout


def test_drawer_wiring(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    chat = client.get("/chat").text
    for marker in ('id="sidebar-toggle"', 'id="scrim"', "drawer.js",
                   'aria-controls="sidebar"', 'aria-expanded="false"'):
        assert marker in chat, marker
    app = client.get("/static/app.js").text
    assert "RunmalDrawer.close()" in app  # selecting a chat closes the drawer
    drawer = client.get("/static/drawer.js").text
    assert "RunmalDrawer" in drawer and "Escape" in drawer

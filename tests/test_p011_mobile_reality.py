"""P-011 acceptance: the mobile reality check.

The record (docs/MOBILE_REALITY_CHECK_2026-10-30.md) decides
Rúnmál's client shape from the tree: browser client everywhere,
no native apps, no on-phone server, PWA as a named future slice.
These tests pin the tree-side facts the record rests on — the
responsive pass's exact extent, the total absence of a PWA
layer, the loopback default, and host-only voice capture — so a
future client slice must update the record deliberately instead
of the record silently going stale.
"""

from __future__ import annotations

from pathlib import Path

from runmal.__main__ import DEFAULT_HOST, DEFAULT_PORT

REPO = Path(__file__).parent.parent
WEB = REPO / "src" / "runmal" / "web"
RECORD = REPO / "docs" / "MOBILE_REALITY_CHECK_2026-10-30.md"

TEMPLATES = (
    "chat.html", "connections.html", "editor.html", "gallery.html",
    "group.html", "inspector.html", "lorebooks.html", "tools.html",
)
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


def _all_web_text() -> str:
    parts = []
    for path in sorted(WEB.rglob("*")):
        if path.is_file() and "__pycache__" not in str(path):
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_templated_page_carries_the_viewport() -> None:
    assert len(TEMPLATES) == 8
    for name in TEMPLATES:
        text = (WEB / "templates" / name).read_text(encoding="utf-8")
        assert VIEWPORT in text, name


def test_responsive_pass_markers_present() -> None:
    css = (WEB / "static" / "style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 1024px)" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (pointer: coarse)" in css
    assert "--touch-target: 44px" in css
    assert "env(safe-area-inset-bottom)" in css


def test_no_pwa_layer_exists_yet() -> None:
    # D2's premise: no manifest, service worker, theme-color or
    # install icons anywhere in the web layer today.
    static_names = {p.name for p in (WEB / "static").iterdir()}
    assert "manifest.json" not in static_names
    assert "manifest.webmanifest" not in static_names
    assert not any("service" in n and "worker" in n for n in static_names)
    assert not any(n.startswith("sw.") for n in static_names)
    assert not any("icon" in n for n in static_names)
    text = _all_web_text()
    assert "serviceWorker" not in text
    assert "theme-color" not in text


def test_server_default_bind_is_loopback() -> None:
    # ADR-0003 / D3: phone reach is an explicit --host act, never
    # the default.
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8098


def test_voice_capture_is_host_side_only() -> None:
    # D5's premise: no browser capture anywhere in the tree; the
    # two server-inline pages sit outside the responsive pass.
    src = REPO / "src" / "runmal"
    offenders = []
    for path in sorted(src.rglob("*")):
        if path.is_file() and "__pycache__" not in str(path):
            if "getUserMedia" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path))
    assert offenders == []
    for rel in ("voice/router.py", "memory/router.py"):
        text = (src / rel).read_text(encoding="utf-8")
        assert "viewport" not in text, rel


def test_record_states_the_decisions() -> None:
    text = RECORD.read_text(encoding="utf-8")
    # D1–D5 are all recorded, with their operative claims.
    for marker in ("**D1", "**D2", "**D3", "**D4", "**D5"):
        assert marker in text, marker
    assert "No native apps" in text
    assert "No on-phone server" in text
    assert "secure context" in text
    # The PWA build and capture slice are flagged for the gate.
    assert "NO HOME" in text and "P-014" in text
    # The rows this record closes the decision half of.
    assert "VX-62" in text and "VX-63" in text
    # Honesty lines: no device evidence is claimed.
    assert "No device was tested" in text

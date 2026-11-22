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

"""S309 acceptance: accessibility pass.

Axe-style rule checks over the templates (landmarks, skip links, labels,
live regions, focus-visible + reduced-motion styles) plus computed WCAG
AA contrast for the token pairs in both themes.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

TEMPLATES = Path(__file__).parent.parent / "src" / "runmal" / "web" / "templates"
CSS = (
    Path(__file__).parent.parent / "src" / "runmal" / "web" / "static" / "style.css"
)
PAGES = ("chat", "connections", "editor", "gallery", "group", "lorebooks", "tools")


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def page_html(name: str) -> str:
    return (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")


# -- WCAG contrast ---------------------------------------------------------

def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def theme_tokens(selector_pattern: str) -> dict[str, str]:
    css = CSS.read_text(encoding="utf-8")
    match = re.search(selector_pattern + r"\s*\{(.*?)\}", css, re.S)
    assert match, selector_pattern
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6});", match.group(1)))


AA = 4.5
PAIRS = (
    ("--text", "--bg"), ("--text", "--panel"), ("--dim", "--bg"),
    ("--dim", "--panel"), ("--accent", "--bg"), ("--accent", "--panel"),
    ("--danger", "--panel"), ("--danger", "--bg"),
    ("--accent-contrast", "--user-bubble"), ("--text", "--code-bg"),
)


def test_contrast_aa_dark_theme():
    tokens = theme_tokens(r":root,\s*\[data-theme=\"dark\"\]")
    for fg, bg in PAIRS:
        ratio = contrast(tokens[fg], tokens[bg])
        assert ratio >= AA, f"dark {fg} on {bg}: {ratio:.2f} < {AA}"


def test_contrast_aa_light_theme():
    tokens = theme_tokens(r"\[data-theme=\"light\"\]")
    for fg, bg in PAIRS:
        ratio = contrast(tokens[fg], tokens[bg])
        assert ratio >= AA, f"light {fg} on {bg}: {ratio:.2f} < {AA}"


# -- Template rules --------------------------------------------------------

def test_landmarks_and_skip_links():
    for name in PAGES:
        html = page_html(name)
        assert "<main" in html, f"{name}: no main landmark"
        assert 'class="skip-link"' in html, f"{name}: no skip link"
        main_id = re.search(r'<main[^>]*id="([^"]+)"', html).group(1)
        assert f'href="#{main_id}"' in html, f"{name}: skip link target mismatch"
        assert 'lang="en"' in html, f"{name}: missing lang"


def test_all_controls_labelled():
    """Every input/select/textarea has a wrapping label, a label[@for],
    or an aria-label. (Hidden inputs exempt.)"""
    for name in PAGES:
        html = page_html(name)
        label_fors = set(re.findall(r'<label[^>]*for="([^"]+)"', html))
        # controls wrapped in a label element
        wrapped = set()
        for m in re.finditer(
            r"<label[^>]*>(.*?)</label>", html, re.S
        ):
            wrapped.update(re.findall(r'id="([^"]+)"', m.group(1)))
        for m in re.finditer(
            r"<(input|select|textarea)\b([^>]*)>", html
        ):
            attrs = m.group(2)
            if 'type="hidden"' in attrs:
                continue
            idm = re.search(r'id="([^"]+)"', attrs)
            cid = idm.group(1) if idm else None
            ok = (
                "aria-label" in attrs
                or (cid and (cid in label_fors or cid in wrapped))
            )
            assert ok, f"{name}: unlabelled control {m.group(0)[:80]}"


def test_streaming_live_region_and_focus_styles(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.get("/chat").text
    assert 'id="sr-status"' in chat and 'aria-live="polite"' in chat
    app = client.get("/static/app.js").text
    assert "announce(" in app and "Reply received" in app
    css = CSS.read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert ".sr-only" in css and ".skip-link" in css


def test_palette_dialog_semantics(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    for route in ("/chat", "/tools", "/group"):
        body = client.get(route).text
        assert 'role="dialog"' in body and 'aria-label="Command palette"' in body
        assert 'role="listbox"' in body
    js = client.get("/static/palette.js").text
    assert 'setAttribute("role", "option")' in js
    assert "aria-selected" in js

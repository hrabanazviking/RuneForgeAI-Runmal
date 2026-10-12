"""S301 acceptance: Hearth design-token tests.

The token layer is the contract: required tokens exist in both themes,
every var() reference resolves, no raw color literals live outside the
token blocks, both layout shells exist, and pages wire the theme control.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

STATIC = Path(__file__).parent.parent / "src" / "runmal" / "web" / "static"
CSS = (STATIC / "style.css").read_text()

COLOR_TOKENS = [
    "--bg", "--panel", "--panel-hover", "--line", "--text", "--dim",
    "--accent", "--accent-contrast", "--user-bubble", "--danger",
    "--danger-bg", "--code-bg", "--overlay",
]
SCALE_TOKENS = [
    "--space-1", "--space-2", "--space-3", "--space-4", "--space-5",
    "--radius-s", "--radius-m", "--radius-l",
    "--font-s", "--font-m", "--font-l", "--sidebar-width", "--content-max",
]


def _block(css: str, start: int) -> str:
    """Return the {...} block starting at the first { at/after `start`."""
    open_idx = css.index("{", start)
    depth = 0
    for i in range(open_idx, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[open_idx : i + 1]
    raise AssertionError("unbalanced CSS")


def _token_block(css: str, marker: str) -> str:
    return _block(css, css.index(marker))


def test_color_tokens_defined_in_both_themes():
    dark = _token_block(CSS, '[data-theme="dark"]')
    light = _token_block(CSS, '[data-theme="light"]')
    for token in COLOR_TOKENS:
        assert f"{token}:" in dark, f"dark missing {token}"
        assert f"{token}:" in light, f"light missing {token}"


def test_light_theme_follows_os_when_no_explicit_choice():
    assert "@media (prefers-color-scheme: light)" in CSS
    block = _token_block(CSS, ":root:not([data-theme])")
    assert "--bg:" in block


def test_scale_tokens_defined():
    for token in SCALE_TOKENS:
        assert f"{token}:" in CSS, f"missing scale token {token}"


def test_every_var_reference_resolves():
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", CSS))
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", CSS))
    assert used <= defined, f"unresolved tokens: {used - defined}"


def _rules(css: str):
    """Yield (selector, body) for every rule, recursing into @media."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i = 0
    while True:
        open_idx = css.find("{", i)
        if open_idx == -1:
            return
        selector = css[i:open_idx].strip()
        depth = 0
        for j in range(open_idx, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        body = css[open_idx + 1 : j]
        if selector.startswith("@media"):
            yield from _rules(body)
        elif selector:
            yield selector, body
        i = j + 1


def _is_token_block(body: str) -> bool:
    decls = [d.strip() for d in body.split(";") if d.strip()]
    return all(
        d.startswith("--") or d.startswith("color-scheme") for d in decls
    )


def test_no_raw_colors_outside_token_blocks():
    offenders = []
    for selector, body in _rules(CSS):
        if _is_token_block(body):
            continue
        if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", body):
            offenders.append(selector)
    assert offenders == [], f"raw colors outside token blocks: {offenders}"


def test_layout_shells_exist():
    assert ".shell {" in CSS and "grid-template-areas" in CSS
    assert ".page {" in CSS


def test_theme_control_wired(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update(
        {"Authorization": f"Bearer {get_or_create_credential()}"}
    )
    chat = client.get("/chat")
    assert 'id="theme-toggle"' in chat.text
    assert "theme.js" in chat.text
    js = client.get("/static/theme.js")
    assert js.status_code == 200
    assert "runmal-theme" in js.text and "data-theme" in js.text
    for page in ("/connections", "/editor", "/tools"):
        body = client.get(page)
        assert 'class="page"' in body.text, page
        assert "theme.js" in body.text, page

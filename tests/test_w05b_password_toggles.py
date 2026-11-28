"""W-05B acceptance: password show/hide toggles everywhere.

Volmarr's standing UI rule (2026-11-27): EVERY password field in
the webface gets a show/hide toggle that reveals or masks what is
typed. Toggling is display-only: it must not change what is
stored or submitted, and it must never weaken the W-04 write-only
secret handling (a stored key never comes back from the engine;
the toggle reveals only what the user is typing).

Field inventory at build time (every password-type input the
webface serves):
  - templates.py _auth_form (login + register + landing):
    name="password" type="password" — hook added in the markup.
  - static/connections.js secretControl (W-04, JS-rendered):
    chat + embedding API key inputs — hook set at render.
  - static/firstrun.js addField(..., password=True) (W-04):
    the backend API-key field — hook set at render.
The shared control is static/pwtoggle.js, loaded by templates'
layout() on every page: inputs marked data-pw-toggle are wrapped
with a Show/Hide button; a MutationObserver wires fields added
dynamically, so future password fields inherit by using the hook.

Tests: (a) served-markup inventory — every password input on the
served pages carries the hook and the shell loads the shared
script; JS-rendered fields asserted at the served-JS level;
(b) the toggle's real behaviour in a headless DOM (node + jsdom;
skips only if that runtime is absent on this machine);
(c) the W-01 auth circuit re-run with the toggle present.
W-04 canary assertions live in test_w04_webface.py (run as the
neighbour battery).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.webface.app import WebfaceApp, make_handler
from runmal.webface.store import Store

REPO = Path(__file__).parent.parent
STATIC = REPO / "src" / "runmal" / "webface" / "static"
HOOK = "data-pw-toggle"
SCRIPT_TAG = '<script src="/static/pwtoggle.js"></script>'


class _StubEngine:
    """Stands in for the engine HTTP API (never for a backend)."""

    def list_characters(self):
        return [{"id": "char-1", "name": "Stub Character"}]

    def list_chats(self):
        return []

    def list_messages(self, chat_id):
        return []


@pytest.fixture()
def webface(tmp_path):
    store = Store(tmp_path)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(WebfaceApp(store, _StubEngine())))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()


def _password_inputs(html_text):
    return [tag for tag in re.findall(r"<input[^>]*>", html_text)
            if 'type="password"' in tag]


def _logged_in_client(webface):
    client = httpx.Client(base_url=webface, follow_redirects=False,
                          trust_env=False)
    reg = client.post("/register", data={
        "username": "w05buser", "password": "long-enough-1"})
    assert reg.status_code == 303
    return client


# ------------------------------------------------- (a) inventory: HTML


def test_every_served_password_input_carries_the_hook(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        for path in ("/", "/login", "/register"):
            page = client.get(path)
            assert page.status_code == 200, path
            inputs = _password_inputs(page.text)
            assert inputs, f"{path}: expected a password input"
            for tag in inputs:
                assert HOOK in tag, f"{path}: password input lacks hook: {tag}"
            assert SCRIPT_TAG in page.text, f"{path}: shell lacks the shared script"
    client = _logged_in_client(webface)
    try:
        for path in ("/connections", "/firstrun", "/chat", "/account"):
            page = client.get(path)
            assert page.status_code == 200, path
            assert SCRIPT_TAG in page.text, f"{path}: shell lacks the shared script"
            for tag in _password_inputs(page.text):
                assert HOOK in tag, f"{path}: password input lacks hook: {tag}"
    finally:
        client.close()


def test_js_rendered_secret_fields_apply_the_hook(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        connections = client.get("/static/connections.js")
        assert connections.status_code == 200
        # secretControl renders both W-04 key inputs (chat + embedding).
        assert 'input.type = "password"' in connections.text
        assert f'input.setAttribute("{HOOK}", "")' in connections.text
        firstrun = client.get("/static/firstrun.js")
        assert firstrun.status_code == 200
        assert 'input.type = "password"' in firstrun.text
        assert f'input.setAttribute("{HOOK}", "")' in firstrun.text


def test_shared_script_shape(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        script = client.get("/static/pwtoggle.js")
        assert script.status_code == 200
    text = script.text
    # The flip is display-only: type password <-> text, value untouched.
    assert 'input.type = show ? "text" : "password"' in text
    assert "aria-pressed" in text and "aria-label" in text
    assert 'b.type = "button"' in text  # the toggle never submits a form
    assert "MutationObserver" in text  # dynamic fields inherit
    assert "RunmalPwToggle" in text
    css = (STATIC / "webface.css").read_text()
    assert ".pw-field" in css and ".pw-toggle" in css


# --------------------------------------- (b) behaviour: headless DOM

_DOM_TEST = r"""
const fs = require("fs");
const { JSDOM } = require("jsdom");
const src = fs.readFileSync(process.argv[2], "utf8");
const dom = new JSDOM(`<!DOCTYPE html><body>
<form method="post" action="/login"><label>Password
<input name="password" type="password" data-pw-toggle value="typed-secret-1"></label>
<button type="submit">Log in</button></form><div id="dyn"></div></body>`,
  { runScripts: "outside-only", url: "http://x/" });
const { window } = dom;
window.eval(src);
const fails = [];
const ok = (n, c) => { if (!c) fails.push(n); console.log((c ? "PASS " : "FAIL ") + n); };
window.addEventListener("load", () => setTimeout(() => {
  const input = window.document.querySelector('input[name="password"]');
  ok("static field wrapped", !!input.closest(".pw-field"));
  const btn = window.document.querySelector(".pw-toggle");
  ok("toggle button exists", !!btn);
  ok("button is type=button", !!btn && btn.type === "button");
  ok("starts Show, aria-pressed false", !!btn && btn.textContent === "Show"
     && btn.getAttribute("aria-pressed") === "false");
  btn.click();
  ok("click flips to text", input.type === "text");
  ok("value unchanged by flip", input.value === "typed-secret-1");
  ok("label flips to Hide", btn.textContent === "Hide"
     && btn.getAttribute("aria-pressed") === "true");
  btn.click();
  ok("second click masks again", input.type === "password" && btn.textContent === "Show");
  const dyn = window.document.createElement("input");
  dyn.type = "password"; dyn.setAttribute("data-pw-toggle", ""); dyn.hidden = true;
  window.document.getElementById("dyn").appendChild(dyn);
  setTimeout(() => {
    ok("dynamic field wrapped by observer", !!dyn.closest(".pw-field"));
    const wrap = dyn.closest(".pw-field");
    const dbtn = wrap ? wrap.querySelector(".pw-toggle") : null;
    ok("dynamic toggle hidden while input hidden", !!dbtn && dbtn.hidden === true);
    dyn.hidden = false;
    setTimeout(() => {
      ok("toggle unhides with input", !!dbtn && dbtn.hidden === false);
      dbtn.click();
      ok("dynamic field flips", dyn.type === "text");
      console.log(fails.length ? "DOMTEST FAILED" : "DOMTEST ALL PASS");
      process.exit(fails.length ? 1 : 0);
    }, 60);
  }, 60);
}, 30));
"""


def test_toggle_behaviour_in_headless_dom(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on this machine")
    probe = subprocess.run([node, "-e", "require.resolve('jsdom')"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("jsdom is not resolvable by node on this machine")
    test_js = tmp_path / "pwtoggle_dom_test.js"
    test_js.write_text(_DOM_TEST)
    run = subprocess.run(
        [node, str(test_js), str(STATIC / "pwtoggle.js")],
        capture_output=True, text=True, timeout=60, cwd=str(Path.home()))
    assert "DOMTEST ALL PASS" in run.stdout, run.stdout + run.stderr
    assert run.returncode == 0, run.stdout + run.stderr


# --------------------------------------------- (c) W-01 auth circuit


def test_auth_circuit_with_toggle_present(webface):
    with httpx.Client(base_url=webface, follow_redirects=False,
                      trust_env=False) as client:
        reg = client.post("/register", data={
            "username": "w05bcircuit", "password": "long-enough-1"})
        assert reg.status_code == 303 and reg.headers["location"] == "/chat"
        assert "webface_session" in reg.headers.get("set-cookie", "")
        assert client.get("/webface/chats").status_code == 200
        client.post("/logout")
        assert client.get("/webface/chats").status_code == 401
        bad = client.post("/login", data={
            "username": "w05bcircuit", "password": "not-the-password"})
        assert "did not match" in bad.text
        # The re-rendered login form still carries the toggle hook.
        for tag in _password_inputs(bad.text):
            assert HOOK in tag
        good = client.post("/login", data={
            "username": "w05bcircuit", "password": "long-enough-1"})
        assert good.status_code == 303
        assert client.get("/webface/chats").status_code == 200

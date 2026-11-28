"""Webface pages: one shell, TABS as the primary navigation.

Every interpolated value is HTML-escaped. Pages for features that
land in later slices render as honest labelled pages ("arrives in
W-NN") — the R-04 house pattern: no dead controls dressed as
features.
"""
from __future__ import annotations

import html

# (slug, label, slice that builds it; None = built in W-01)
TABS: list[tuple[str, str, str | None]] = [
    ("chat", "Chat", None),
    ("groups", "Groups", None),
    ("characters", "Characters", None),
    ("library", "Library", None),
    ("personas", "Personas", "W-05"),
    ("lorebooks", "Lorebooks", "W-05"),
    ("connections", "Connections", None),
    ("generation", "Generation", None),
    ("memory", "Memory", "W-06"),
    ("scenarios", "Scenarios", "W-06"),
    ("inspector", "Inspector", "W-07"),
    ("tools", "Tools", "W-07"),
    ("voice", "Voice", "W-08"),
    ("vision", "Vision", "W-08"),
    ("backups", "Backups", "W-09"),
    ("plugins", "Plugins", "W-09"),
    ("appearance", "Appearance", "W-09"),
    ("account", "Account", None),
]

TAB_SLUGS = {slug for slug, _label, _slice in TABS}
PENDING = {slug: (label, sl) for slug, label, sl in TABS if sl}


def e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def layout(title, body, user=None, active_tab=None, flash=None,
           flash_err=False):
    if user:
        tabs = "".join(
            f'<a class="tab{" active" if slug == active_tab else ""}"'
            f' href="/{slug}">{e(label)}</a>'
            for slug, label, _sl in TABS)
        nav = (f'<nav class="tabs">{tabs}</nav>'
               f'<div class="who">Signed in as '
               f'<b>{e(user["username"])}</b> '
               f'<span class="tag">{e(user["account_type"])}</span> '
               '<form method="post" action="/logout" class="inline">'
               '<button class="btn ghost small" type="submit">'
               "Log out</button></form></div>")
    else:
        nav = ('<nav class="tabs"><a class="tab" href="/login">Log in</a>'
               '<a class="tab" href="/register">Register</a></nav>')
    flash_html = (f'<div class="flash{" err" if flash_err else ""}">'
                  f"{e(flash)}</div>") if flash else ""
    return ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">"
            f"<title>{e(title)} — Rúnmál</title>"
            "<link rel=\"stylesheet\" href=\"/static/webface.css\">"
            "</head><body>"
            "<header class=\"face-head\"><div class=\"wrap\">"
            "<a class=\"brand\" href=\"/\">ᚱ Rúnmál</a>"
            f"{nav}</div></header>"
            f"<main class=\"wrap\">{flash_html}{body}</main>"
            "<footer class=\"face-foot wrap\">Rúnmál web face — "
            "the same engine, the same history, on every device."
            "</footer></body></html>")


def _auth_form(action, heading, button, error=None):
    err = f'<div class="flash err">{e(error)}</div>' if error else ""
    return (f"<section class=\"card auth\"><h1>{e(heading)}</h1>{err}"
            f'<form method="post" action="{action}">'
            '<label>Username<input name="username" required '
            'autocomplete="username"></label>'
            '<label>Password<input name="password" type="password" '
            'required autocomplete="current-password"></label>'
            f'<button class="btn" type="submit">{e(button)}</button>'
            "</form></section>")


def landing_page(error=None):
    """The account page: what a logged-out visitor meets first
    (Volmarr's entry flow, 2026-11-27 ~18:12 EST)."""
    body = ("<section class=\"hero\"><h1>Rúnmál</h1>"
            "<p>Your sovereign AI chat hall — the same characters, the "
            "same history, from any device on your tailnet. Sign in, "
            "or make an account, and the hall opens at the Chat tab.</p>"
            "</section>"
            + _auth_form("/login", "Log in", "Log in", error)
            + '<p class="muted center">New here? '
            '<a href="/register">Register an account</a>.</p>')
    return layout("Welcome", body, user=None)


def login_page(error=None):
    return layout("Log in", _auth_form("/login", "Log in", "Log in", error),
                  user=None)


def register_page(error=None):
    body = (_auth_form("/register", "Register", "Create account", error)
            + '<p class="muted center">Already have an account? '
            '<a href="/login">Log in</a>.</p>')
    return layout("Register", body, user=None)


def account_page(user, session_expires_text):
    body = ("<section class=\"card\"><h1>Account</h1>"
            f"<p>Username: <b>{e(user['username'])}</b></p>"
            f"<p>Account type: <span class=\"tag\">"
            f"{e(user['account_type'])}</span></p>"
            f"<p>Session valid until: {e(session_expires_text)}</p>"
            '<p><a href="/firstrun">First-Run Setup</a> - connect a mind, meet someone, set '
            'your name.</p>'
            '<form method="post" action="/logout">'
            '<button class="btn ghost" type="submit">Log out</button>'
            "</form>"
            "<p class=\"muted\">Password change, recovery codes and "
            "agent API tokens arrive in W-10.</p></section>")
    return layout("Account", body, user=user, active_tab="account")


def pending_page(user, slug):
    label, slice_name = PENDING[slug]
    body = (f"<section class=\"card\"><h1>{e(label)}</h1>"
            f"<p>This tab arrives in slice <b>{e(slice_name)}</b> of "
            "the Rúnmál Web Access campaign. The tab is here from "
            "the first day so the hall's shape is whole; the feature "
            "itself is not built yet, and nothing on this page "
            "pretends otherwise.</p></section>")
    return layout(label, body, user=user, active_tab=slug)


def chat_page(user):
    body = ("<div class=\"chat-shell\">"
            "<aside class=\"chat-side card\">"
            "<label>Character<select id=\"char-select\"></select></label>"
            "<div id=\"firstrun-banner\" hidden><p>New here? <a href=\"/firstrun\">Run "
            "First-Run Setup</a> - connect a mind and meet someone. <button "
            "id=\"firstrun-dismiss\" class=\"btn ghost small\" "
            "type=\"button\">Dismiss</button></p></div>"
            "<label>Preset for the open chat<select id=\"preset-select\"></select></label>"
            "<button id=\"preset-apply\" class=\"btn ghost\" type=\"button\">Apply preset</button>"
            "<button id=\"new-chat\" class=\"btn\" type=\"button\">"
            "New chat</button>"
            "<ul id=\"chat-list\" class=\"chat-list\"></ul>"
            "</aside>"
            "<section class=\"chat-main card\">"
            "<div id=\"messages\" class=\"messages\"></div>"
            "<div class=\"composer\">"
            "<textarea id=\"composer\" rows=\"3\" "
            "placeholder=\"Write a message…\"></textarea>"
            "<button id=\"send\" class=\"btn\" type=\"button\">Send</button>"
            "<button id=\"stop\" class=\"btn ghost\" type=\"button\" "
            "disabled>Stop</button>"
            "</div>"
            "<p id=\"chat-status\" class=\"muted\"></p>"
            "<h2>Message actions</h2>"
            "<p class=\"muted\">Pick a message, then act on it. Swipe "
            "position and pin state are written on each row.</p>"
            "<ul id=\"msg-list\" class=\"chat-list\"></ul>"
            "<div class=\"row\">"
            "<button id=\"m-edit\" class=\"btn small\" type=\"button\">Edit…</button>"
            "<button id=\"m-delete\" class=\"btn small ghost\" type=\"button\">Delete</button>"
            "<button id=\"m-prev\" class=\"btn small ghost\" type=\"button\">◀ Swipe</button>"
            "<button id=\"m-next\" class=\"btn small ghost\" type=\"button\">Swipe ▶</button>"
            "<button id=\"m-swipes\" class=\"btn small ghost\" type=\"button\">Swipes…</button>"
            "<button id=\"m-branch\" class=\"btn small ghost\" type=\"button\">Branch…</button>"
            "<button id=\"m-pin\" class=\"btn small ghost\" type=\"button\">Pin/Unpin</button>"
            "<button id=\"m-copy\" class=\"btn small ghost\" type=\"button\">Copy</button>"
            "</div>"
            "<div id=\"msg-panel\"></div>"
            "<h2>Chat actions</h2>"
            "<div class=\"row\">"
            "<button id=\"a-regen\" class=\"btn small\" type=\"button\">Regenerate</button>"
            "<button id=\"a-continue\" class=\"btn small ghost\" type=\"button\">Continue</button>"
            "<button id=\"a-impersonate\" class=\"btn small ghost\" "
            "type=\"button\">Impersonate…</button>"
            "<button id=\"a-note\" class=\"btn small ghost\" "
            "type=\"button\">Author's Note…</button>"
            "<button id=\"a-search\" class=\"btn small ghost\" "
            "type=\"button\">Search Chats…</button>"
            "<button id=\"a-checkpoints\" class=\"btn small ghost\" "
            "type=\"button\">Checkpoints &amp; Undo…</button>"
            "</div>"
            "<div id=\"chat-panel\"></div>"
            "</section></div>"
            "<script src=\"/static/chat.js\"></script>")
    return layout("Chat", body, user=user, active_tab="chat")


def groups_page(user):
    body = ("<section class=\"card\"><h1>Groups</h1>"
            "<div class=\"row\">"
            "<label>Room name<input id=\"g-name\"></label>"
            "<button id=\"g-create\" class=\"btn\" type=\"button\">Create room</button></div>"
            "<p class=\"muted\">Tick the roster for the new room:</p>"
            "<div id=\"g-roster-pick\"></div>"
            "<ul id=\"g-list\" class=\"roster\"></ul>"
            "<p id=\"g-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"g-room\" hidden></section>"
            "<script src=\"/static/groups.js\"></script>")
    return layout("Groups", body, user=user, active_tab="groups")
def characters_page(user):
    body = ("<section class=\"card\"><h1>Characters</h1>"
            "<div class=\"row\">"
            "<label>Search<input id=\"c-search\"></label>"
            "<label>Tag<select id=\"c-tag\"><option value=\"\">All tags</option></select></label>"
            "<label class=\"check\"><input type=\"checkbox\" id=\"c-fav\"> Favourites only</label>"
            "<button id=\"c-new\" class=\"btn\" type=\"button\">New character</button></div>"
            "<p id=\"c-census\" class=\"muted\"></p>"
            "<ul id=\"c-roster\" class=\"roster\"></ul>"
            "<p id=\"c-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"c-editor\" hidden></section>"
            "<script src=\"/static/characters.js\"></script>")
    return layout("Characters", body, user=user, active_tab="characters")


def library_page(user):
    body = ("<section class=\"card\"><h1>Library</h1>"
            "<h2>Import character cards</h2>"
            "<p>Import JSON or PNG character cards. The file you pick is "
            "read as-is and handed to the engine; the web face never "
            "deletes it.</p>"
            "<label>Card files<input id=\"l-files\" type=\"file\" "
            "multiple accept=\".json,.png\"></label>"
            "<button id=\"l-import\" class=\"btn\" type=\"button\">Import</button>"
            "<p id=\"l-result\" class=\"muted\"></p>"
            "<ul id=\"l-lines\"></ul>"
            "<h2>Cards</h2>"
            "<div class=\"row\"><label>Search<input id=\"l-search\"></label>"
            "<label>Tag<select id=\"l-tag\"><option value=\"\">All tags</option></select></label>"
            "<label class=\"check\"><input type=\"checkbox\" id=\"l-fav\"> "
            "Favourites only</label></div>"
            "<p id=\"l-census\" class=\"muted\"></p>"
            "<ul id=\"l-roster\" class=\"roster\"></ul>"
            "<p id=\"l-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/library.js\"></script>")
    return layout("Library", body, user=user, active_tab="library")


def connections_page(user):
    body = ("<section class=\"card\"><h1>Connections</h1>"
            "<p>Backend profiles: the minds Runmal can think with. "
            "API keys are write-only - you can set or clear one, and "
            "the page only ever says whether a key is stored.</p>"
            "<ul id=\"p-list\" class=\"roster\"></ul>"
            "<p id=\"p-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"p-editor\" hidden></section>"
            "<section class=\"card\"><h2>Pin a profile to a chat</h2>"
            "<p>There is no default profile: a chat answers through "
            "the profile pinned to it, or the engine default when "
            "nothing is pinned.</p>"
            "<div class=\"row\"><label>Chat<select id=\"pin-chat\"></select></label>"
            "<label>Profile<select id=\"pin-profile\"></select></label>"
            "<button id=\"pin-apply\" class=\"btn\" type=\"button\">Pin</button>"
            "<button id=\"pin-clear\" class=\"btn ghost\" type=\"button\">Unpin</button></div>"
            "<p id=\"pin-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/connections.js\"></script>")
    return layout("Connections", body, user=user, active_tab="connections")


def generation_page(user):
    body = ("<section class=\"card\"><h1>Generation</h1>"
            "<h2>Presets</h2><ul id=\"g-presets\" class=\"roster\"></ul>"
            "<p id=\"g-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"g-editor\" hidden></section>"
            "<section class=\"card\"><h2>Bundles</h2>"
            "<ul id=\"g-bundles\" class=\"roster\"></ul></section>"
            "<section class=\"card\" id=\"g-bundle-editor\" hidden></section>"
            "<section class=\"card\"><h2>Per-chat override</h2>"
            "<div class=\"row\"><label>Chat<select id=\"ov-chat\"></select></label>"
            "<label>Bundle<select id=\"ov-bundle\"></select></label></div>"
            "<div id=\"ov-form\"></div>"
            "<div class=\"row\"><button id=\"ov-save\" class=\"btn\" type=\"button\">Save "
            "override</button>"
            "<button id=\"ov-delete\" class=\"btn ghost\" type=\"button\">Delete "
            "override</button></div>"
            "<p id=\"ov-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Resolve preview</h2>"
            "<div class=\"row\"><label>Chat<select id=\"rv-chat\"></select></label>"
            "<button id=\"rv-show\" class=\"btn\" type=\"button\">Show what a send will "
            "use</button></div>"
            "<div id=\"rv-out\"></div></section>"
            "<script src=\"/static/generation.js\"></script>")
    return layout("Generation", body, user=user, active_tab="generation")


def firstrun_page(user):
    body = ("<section class=\"card\"><h1>First-Run Setup</h1>"
            "<p id=\"fr-state\" class=\"muted\"></p>"
            "<h2>1. Connect a mind</h2><div id=\"fr-minds\"></div>"
            "<div id=\"fr-connect\"></div>"
            "<h2>2. Prove it</h2><p id=\"fr-prove\" class=\"muted\">Connect a mind first.</p>"
            "<h2>3. Meet someone</h2><div id=\"fr-meet\"></div>"
            "<h2>4. Your name</h2>"
            "<div class=\"row\"><label>Your name<input id=\"fr-name\"></label>"
            "<button id=\"fr-name-save\" class=\"btn\" type=\"button\">Save name</button></div>"
            "<p id=\"fr-status\" class=\"muted\"></p>"
            "<p><button id=\"fr-finish\" class=\"btn\" type=\"button\" disabled>Finish - "
            "open the greeted chat</button></p>"
            "</section><script src=\"/static/firstrun.js\"></script>")
    return layout("First-Run Setup", body, user=user, active_tab="account")

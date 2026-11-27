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
    ("groups", "Groups", "W-03"),
    ("characters", "Characters", None),
    ("library", "Library", None),
    ("personas", "Personas", "W-05"),
    ("lorebooks", "Lorebooks", "W-05"),
    ("connections", "Connections", "W-04"),
    ("generation", "Generation", "W-04"),
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
            "</section></div>"
            "<script src=\"/static/chat.js\"></script>")
    return layout("Chat", body, user=user, active_tab="chat")


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

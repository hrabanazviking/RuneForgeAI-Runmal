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
    ("personas", "Personas", None),
    ("lorebooks", "Lorebooks", None),
    ("connections", "Connections", None),
    ("generation", "Generation", None),
    ("memory", "Memory", None),
    ("scenarios", "Scenarios", None),
    ("inspector", "Inspector", None),
    ("tools", "Tools", None),
    ("voice", "Voice", None),
    ("vision", "Vision", None),
    ("backups", "Backups", None),
    ("plugins", "Plugins", None),
    ("bridge", "Bridge", None),
    ("appearance", "Appearance", None),
    ("account", "Account", None),
]

TAB_SLUGS = {slug for slug, _label, _slice in TABS}
PENDING = {slug: (label, sl) for slug, label, sl in TABS if sl}


def e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def layout(title, body, user=None, active_tab=None, flash=None,
           flash_err=False):
    appearance_style = ""
    if user:
        from . import w09 as _w09
        prefs = _w09.normalize_appearance(user.get("appearance"))
        css = _w09.appearance_css(prefs)
        if css:
            appearance_style = (
                f'<style id="appearance-css">{css}</style>')
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
            f"{appearance_style}"
            "</head><body>"
            "<header class=\"face-head\"><div class=\"wrap\">"
            "<a class=\"brand\" href=\"/\">ᚱ Rúnmál</a>"
            f"{nav}</div></header>"
            f"<main class=\"wrap\">{flash_html}{body}</main>"
            "<footer class=\"face-foot wrap\">Rúnmál web face — "
            "the same engine, the same history, on every device."
            "</footer>"
            "<script src=\"/static/pwtoggle.js\"></script>"
            "</body></html>")


def _auth_form(action, heading, button, error=None):
    err = f'<div class="flash err">{e(error)}</div>' if error else ""
    return (f"<section class=\"card auth\"><h1>{e(heading)}</h1>{err}"
            f'<form method="post" action="{action}">'
            '<label>Username<input name="username" class=\"entry-box\" required '
            'autocomplete="username"></label>'
            '<label>Password<input name="password" type="password" data-pw-toggle '
            'class=\"entry-box\" '
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
            '<a href="/register">Register an account</a>. Locked out? '
            '<a href="/recover">Recover your account</a>.</p>')
    return layout("Welcome", body, user=None)


def login_page(error=None, note=None):
    note_html = f'<div class="flash">{e(note)}</div>' if note else ""
    body = (note_html + _auth_form("/login", "Log in", "Log in", error)
            + '<p class="muted center">Locked out? '
            '<a href="/recover">Recover your account</a>.</p>')
    return layout("Log in", body, user=None)


def register_page(error=None):
    body = (_auth_form("/register", "Register", "Create account", error)
            + '<p class="muted center">Already have an account? '
            '<a href="/login">Log in</a>.</p>')
    return layout("Register", body, user=None)


def account_page(user, session_expires_text, data=None, flash=None,
                 flash_err=False, codes_once=None, token_once=None):
    from . import w10 as _w10
    data = data or {"sessions": [], "tokens": []}
    parts = ["<section class=\"card\"><h1>Account</h1>"]
    if flash:
        parts.append(
            f'<div class="flash{" err" if flash_err else ""}">{e(flash)}</div>')
    parts.append(f"<p>Username: <b>{e(user['username'])}</b></p>")
    parts.append(
        f"<p>Account type: <span class=\"tag\">"
        f"{e(user['account_type'])}</span></p>")
    parts.append(f"<p>Session valid until: {e(session_expires_text)}</p>")
    parts.append(
        '<p><a href="/firstrun">First-Run Setup</a> - connect a mind, '
        'meet someone, set your name.</p>')
    # -- change password --
    parts.append("<h2>Change password</h2>")
    parts.append(f"<p class=\"muted\">{e(_w10.CHANGE_WORDS)}</p>")
    parts.append(
        '<form method="post" action="/account/password">'
        '<label>Current password<input name="current_password" '
        'type="password" data-pw-toggle class=\"entry-box\" required '
        'autocomplete="current-password"></label>'
        '<label>New password<input name="new_password" '
        'type="password" data-pw-toggle class=\"entry-box\" required '
        'autocomplete="new-password"></label>'
        '<button class="btn" type="submit">Change password</button>'
        "</form>")
    # -- recovery codes --
    parts.append("<h2>Recovery codes</h2>")
    parts.append(
        "<p class=\"muted\">One-time codes that set a new password "
        "from the recovery page when you are locked out. Generating "
        "a set replaces any earlier set.</p>")
    if codes_once:
        listing = "".join(f"<li><code>{e(c)}</code></li>" for c in codes_once)
        parts.append(
            f"<p><b>{e(_w10.RECOVERY_ONCE_WORDS)}</b></p>"
            f"<ul class=\"roster\">{listing}</ul>")
    parts.append(
        '<form method="post" action="/account/recovery-codes">'
        '<button class="btn ghost" type="submit">Generate recovery '
        "codes</button></form>")
    # -- sessions --
    parts.append("<h2>Sessions</h2>")
    if data["sessions"]:
        rows = "".join(
            f"<li>Started {e(_fmt(row['created_at']))} - valid until "
            f"{e(_fmt(row['expires']))}</li>" for row in data["sessions"])
        parts.append(f"<ul class=\"roster\">{rows}</ul>")
    else:
        parts.append("<p class=\"muted\">No live sessions.</p>")
    parts.append(
        '<form method="post" action="/account/sign-out-everywhere">'
        '<button class="btn ghost" type="submit">Sign out '
        "everywhere</button></form>")
    # -- agent tokens --
    parts.append("<h2>Agent API tokens</h2>")
    parts.append(f"<p class=\"muted\">{e(_w10.AGENT_SCOPE_WORDS)}</p>")
    if token_once:
        parts.append(
            f"<p><b>{e(_w10.TOKEN_ONCE_WORDS)}</b></p>"
            f"<p><code>{e(token_once)}</code></p>")
    if data["tokens"]:
        rows = ""
        for t in data["tokens"]:
            rows += (
                f"<li>{e(t['name'])} - {e(t['state'])} - created "
                f"{e(_fmt(t['created_at']))}")
            if t["state"] == "active":
                rows += (
                    f' <form method="post" class="inline" '
                    f'action="/account/agent-tokens/{t["id"]}/revoke">'
                    '<button class="btn ghost small" type="submit">'
                    "Revoke</button></form>")
            rows += "</li>"
        parts.append(f"<ul class=\"roster\">{rows}</ul>")
    else:
        parts.append("<p class=\"muted\">No agent tokens yet.</p>")
    parts.append(
        '<form method="post" action="/account/agent-tokens">'
        '<label>Token name<input name="name" class=\"entry-box\" '
        'required></label>'
        '<button class="btn" type="submit">Create agent token</button>'
        "</form>")
    parts.append(
        '<form method="post" action="/logout">'
        '<button class="btn ghost" type="submit">Log out</button>'
        "</form></section>")
    return layout("Account", "".join(parts), user=user,
                  active_tab="account")


def _fmt(ts):
    from datetime import UTC, datetime
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).strftime(
            "%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return str(ts)


def recover_page(error=None):
    err = f'<div class="flash err">{e(error)}</div>' if error else ""
    body = ("<section class=\"card auth\"><h1>Recover your account</h1>"
            f"{err}"
            "<p>Enter your username, one recovery code, and a new "
            "password. The code works once; every session for the "
            "account is closed and you log in fresh.</p>"
            '<form method="post" action="/recover">'
            '<label>Username<input name="username" class=\"entry-box\" '
            'required autocomplete="username"></label>'
            '<label>Recovery code<input name="code" class=\"entry-box\" '
            'required autocomplete="one-time-code"></label>'
            '<label>New password<input name="new_password" '
            'type="password" data-pw-toggle class=\"entry-box\" required '
            'autocomplete="new-password"></label>'
            '<button class="btn" type="submit">Set new password</button>'
            "</form></section>")
    return layout("Recover", body, user=None)


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
            "<label>Character<select id=\"char-select\" class=\"entry-box\"></select></label>"
            "<div id=\"firstrun-banner\" hidden><p>New here? <a href=\"/firstrun\">Run "
            "First-Run Setup</a> - connect a mind and meet someone. <button "
            "id=\"firstrun-dismiss\" class=\"btn ghost small\" "
            "type=\"button\">Dismiss</button></p></div>"
            "<label>Preset for the open chat<select id=\"preset-select\" class=\"entry-box\">"
            "</select></label>"
            "<button id=\"preset-apply\" class=\"btn ghost\" type=\"button\">Apply preset</button>"
            "<button id=\"new-chat\" class=\"btn\" type=\"button\">"
            "New chat</button>"
            "<ul id=\"chat-list\" class=\"chat-list\"></ul>"
            "</aside>"
            "<section class=\"chat-main card\">"
            "<p id=\"mind-line\" class=\"mind-line\"></p>"
            "<div id=\"messages\" class=\"messages\"></div>"
            "<div id=\"no-mind\"></div>"
            "<div class=\"composer\">"
            "<textarea id=\"composer\" rows=\"3\" "
            "placeholder=\"Write a message…\" class=\"entry-box\"></textarea>"
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
            "<label>Room name<input id=\"g-name\" class=\"entry-box\"></label>"
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
            "<label>Search<input id=\"c-search\" class=\"entry-box\"></label>"
            "<label>Tag<select id=\"c-tag\" class=\"entry-box\">"
            "<option value=\"\">All tags</option></select></label>"
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
            "<div class=\"row\"><label>Search<input id=\"l-search\" class=\"entry-box\"></label>"
            "<label>Tag<select id=\"l-tag\" class=\"entry-box\">"
            "<option value=\"\">All tags</option></select></label>"
            "<label class=\"check\"><input type=\"checkbox\" id=\"l-fav\"> "
            "Favourites only</label></div>"
            "<p id=\"l-census\" class=\"muted\"></p>"
            "<ul id=\"l-roster\" class=\"roster\"></ul>"
            "<p id=\"l-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Library search</h2>"
            "<p>One search across the library, as the desktop's "
            "Library Search dialog runs it: the hub (entry "
            "descriptions and verified pack contents) always, "
            "and one chat's bound workspace folder when you "
            "name the chat. Both searches are literal - the "
            "engines' own law.</p>"
            "<div class=\"row\"><label>Search<input id=\"ls-q\" "
            "class=\"entry-box\"></label>"
            "<label>Kind<select id=\"ls-kind\" class=\"entry-box\">"
            "<option value=\"\">All kinds</option>"
            "<option value=\"lorebook_pack\">Lorebook packs</option>"
            "<option value=\"scenario_pack\">Scenario packs</option>"
            "<option value=\"preset_bundle\">Preset bundles</option>"
            "<option value=\"prompt_pack\">Prompt packs</option>"
            "</select></label>"
            "<label>Chat workspace<select id=\"ls-chat\" class=\"entry-box\">"
            "<option value=\"\">No workspace</option></select></label>"
            "<button id=\"ls-go\" class=\"btn\" type=\"button\">"
            "Search</button></div>"
            "<pre id=\"ls-words\" class=\"words\"></pre>"
            "<ul id=\"ls-results\" class=\"roster\"></ul>"
            "<p id=\"ls-faces\" class=\"muted\"></p>"
            "<p id=\"ls-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/library.js\"></script>"
            "<script src=\"/static/search.js\"></script>")
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
            "<div class=\"row\"><label>Chat<select id=\"pin-chat\" class=\"entry-box\"></select>"
            "</label>"
            "<label>Profile<select id=\"pin-profile\" class=\"entry-box\"></select></label>"
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
            "<div class=\"row\"><label>Chat<select id=\"ov-chat\" class=\"entry-box\"></select>"
            "</label>"
            "<label>Bundle<select id=\"ov-bundle\" class=\"entry-box\"></select></label></div>"
            "<div id=\"ov-form\"></div>"
            "<div class=\"row\"><button id=\"ov-save\" class=\"btn\" type=\"button\">Save "
            "override</button>"
            "<button id=\"ov-delete\" class=\"btn ghost\" type=\"button\">Delete "
            "override</button></div>"
            "<p id=\"ov-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Resolve preview</h2>"
            "<div class=\"row\"><label>Chat<select id=\"rv-chat\" class=\"entry-box\"></select>"
            "</label>"
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
            "<div class=\"row\"><label>Your name<input id=\"fr-name\" class=\"entry-box\"></label>"
            "<button id=\"fr-name-save\" class=\"btn\" type=\"button\">Save name</button></div>"
            "<p id=\"fr-status\" class=\"muted\"></p>"
            "<p><button id=\"fr-finish\" class=\"btn\" type=\"button\" disabled>Finish - "
            "open the greeted chat</button></p>"
            "</section><script src=\"/static/firstrun.js\"></script>")
    return layout("First-Run Setup", body, user=user, active_tab="account")


def personas_page(user):
    body = ("<section class=\"card\"><h1>Personas</h1>"
            "<h2>Your name</h2>"
            "<p id=\"pn-current\" class=\"muted\">Loading...</p>"
            "<div class=\"row\"><label>Your name in chats"
            "<input id=\"pn-name\" class=\"entry-box\"></label>"
            "<button id=\"pn-save\" class=\"btn\" type=\"button\">Save name</button>"
            "<button id=\"pn-clear\" class=\"btn ghost\" type=\"button\">Clear name</button></div>"
            "<p class=\"muted\">An empty field never clears the name - "
            "clearing is the Clear button's own act, and it returns "
            "you to the built-in default.</p>"
            "<p id=\"pn-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Per-chat persona</h2>"
            "<p>A chat's persona is the character that chat speaks "
            "with. Pick a chat, see its persona, switch it or clear "
            "it.</p>"
            "<div class=\"row\"><label>Chat<select id=\"pp-chat\" class=\"entry-box\"></select>"
            "</label>"
            "<label>Persona character<select id=\"pp-char\" class=\"entry-box\"></select></label>"
            "</div>"
            "<p id=\"pp-current\" class=\"muted\"></p>"
            "<div class=\"row\"><button id=\"pp-switch\" class=\"btn\" "
            "type=\"button\">Switch persona</button>"
            "<button id=\"pp-clear\" class=\"btn ghost\" "
            "type=\"button\">Clear persona</button></div>"
            "<p class=\"muted\">Switching a chat's persona shapes "
            "FUTURE turns only; messages already stored keep the "
            "speaker they were written with. The Chat tab reads the "
            "same engine record, so both views agree.</p>"
            "<p id=\"pp-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Persona files</h2>"
            "<p>The engine library defines a persona-file format, "
            "but no engine route serves it, so this page offers no "
            "persona import or export - there is nothing honest to "
            "wire a button to.</p></section>"
            "<script src=\"/static/personas.js\"></script>")
    return layout("Personas", body, user=user, active_tab="personas")


def lorebooks_page(user):
    body = ("<section class=\"card\"><h1>Lorebooks</h1>"
            "<ul id=\"lb-list\" class=\"roster\"></ul>"
            "<p id=\"lb-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"lb-editor\" hidden></section>"
            "<section class=\"card\" id=\"lb-entries\" hidden></section>"
            "<section class=\"card\" id=\"lb-entry-editor\" hidden></section>"
            "<section class=\"card\" id=\"lb-scopes\" hidden></section>"
            "<section class=\"card\" id=\"lb-previews\" hidden></section>"
            "<section class=\"card\"><h2>Import, packs and upgrades</h2>"
            "<p>Import a lorebook document (native or world-info "
            "shape), inspect or import a sharing pack, or check / "
            "upgrade an older lorebook file. Upgrading a file "
            "changes only the file - download the result, then "
            "import it if you want it in the library.</p>"
            "<label>Lorebook / pack file<input id=\"lb-file\" "
            "type=\"file\" accept=\".json\"></label>"
            "<div class=\"row\">"
            "<button id=\"lb-import\" class=\"btn\" type=\"button\">Import document</button>"
            "<button id=\"lb-pack-inspect\" class=\"btn ghost\" "
            "type=\"button\">Inspect pack</button>"
            "<button id=\"lb-pack-import\" class=\"btn ghost\" type=\"button\">Import pack</button>"
            "<button id=\"lb-upgrade-inspect\" class=\"btn ghost\" "
            "type=\"button\">Inspect upgrade</button>"
            "<button id=\"lb-upgrade\" class=\"btn ghost\" "
            "type=\"button\">Upgrade file</button></div>"
            "<p id=\"lb-transfer-status\" class=\"muted\"></p>"
            "<div id=\"lb-transfer-out\"></div></section>"
            "<script src=\"/static/lorebooks.js\"></script>")
    return layout("Lorebooks", body, user=user, active_tab="lorebooks")


def memory_page(user):
    body = ("<section class=\"card\"><h1>Memory</h1>"
            "<p>What the engine remembers, with where each memory "
            "came from. Memories are read here - the engine offers "
            "no road to create, edit or delete one by hand.</p>"
            "<div class=\"row\"><label>Search<input id=\"m-search\" class=\"entry-box\"></label>"
            "<label>State<select id=\"m-state\" class=\"entry-box\">"
            "<option value=\"\">Any state</option></select></label>"
            "<label>Kind<select id=\"m-kind\" class=\"entry-box\">"
            "<option value=\"\">Any kind</option></select></label>"
            "<button id=\"m-go\" class=\"btn\" type=\"button\">Search</button></div>"
            "<p id=\"m-count\" class=\"muted\"></p>"
            "<ul id=\"m-list\" class=\"roster\"></ul>"
            "<p id=\"m-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"m-detail\" hidden></section>"
            "<section class=\"card\"><h2>Embedding</h2>"
            "<p id=\"m-embed-note\" class=\"muted\"></p></section>"
            "<script src=\"/static/memory.js\"></script>")
    return layout("Memory", body, user=user, active_tab="memory")


def scenarios_page(user):
    body = ("<section class=\"card\"><h1>Scenarios</h1>"
            "<div class=\"row\"><label>Search<input id=\"s-search\" class=\"entry-box\"></label>"
            "<label class=\"check\"><input type=\"checkbox\" id=\"s-fav\"> Favourites only</label>"
            "<button id=\"s-new\" class=\"btn\" type=\"button\">New scenario</button></div>"
            "<p id=\"s-count\" class=\"muted\"></p>"
            "<ul id=\"s-list\" class=\"roster\"></ul>"
            "<p id=\"s-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"s-editor\" hidden></section>"
            "<section class=\"card\"><h2>Bindings</h2>"
            "<p>Chats a scenario has been bound to. Unbinding removes "
            "only the binding record - seeded lines stay.</p>"
            "<ul id=\"s-bindings\" class=\"roster\"></ul>"
            "<p id=\"s-bind-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Import a scenario file</h2>"
            "<p>Checking a file parses it and reports what mapped "
            "and what was unmappable - nothing is stored. Storing "
            "keeps the parsed scenario as a new definition.</p>"
            "<label>Scenario file<input id=\"s-file\" type=\"file\" accept=\".json\"></label>"
            "<div class=\"row\"><button id=\"s-check\" class=\"btn ghost\" "
            "type=\"button\">Check file</button>"
            "<button id=\"s-store\" class=\"btn\" type=\"button\">"
            "Store this scenario</button></div>"
            "<p id=\"s-import-status\" class=\"muted\"></p>"
            "<div id=\"s-import-out\"></div></section>"
            "<script src=\"/static/scenarios.js\"></script>")
    return layout("Scenarios", body, user=user, active_tab="scenarios")


def inspector_page(user):
    body = ("<section class=\"card\"><h1>Inspector</h1>"
            "<p>For the chat you pick: what the next turn's prompt "
            "would contain, slot by slot, and why - plus the "
            "chat's overview, events and reasoning records, and "
            "the recorded provenance of any landed reply.</p>"
            "<div class=\"row\"><label>Chat<select id=\"i-chat\" class=\"entry-box\"></select>"
            "</label>"
            "<button id=\"i-load\" class=\"btn\" type=\"button\">Inspect</button>"
            "<button id=\"i-trace\" class=\"btn ghost\" type=\"button\">"
            "Run the trace</button></div>"
            "<p id=\"i-note\" class=\"muted\"></p>"
            "<p id=\"i-status\" class=\"muted\"></p></section>"
            "<section class=\"card\" id=\"i-trace-box\" hidden><h2>Prompt trace</h2>"
            "<p id=\"i-ledger\"></p><ul id=\"i-slots\" class=\"roster\"></ul>"
            "<pre id=\"i-lore\" class=\"words\"></pre>"
            "<p id=\"i-content-note\" class=\"muted\"></p>"
            "<h3>Composed sections (from the preview payload)</h3>"
            "<div id=\"i-sections\"></div>"
            "<pre id=\"i-preview-words\" class=\"words\"></pre></section>"
            "<section class=\"card\" id=\"i-docs\" hidden><h2>Overview</h2>"
            "<pre id=\"i-overview\" class=\"words\"></pre>"
            "<h2>Events</h2><pre id=\"i-events\" class=\"words\"></pre>"
            "<h2>Reasoning</h2><pre id=\"i-reasoning\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Reply provenance</h2>"
            "<p>Pick a landed reply to see the provenance the "
            "engine recorded for it.</p>"
            "<ul id=\"i-messages\" class=\"roster\"></ul>"
            "<pre id=\"i-prov\" class=\"words\"></pre></section>"
            "<script src=\"/static/inspector.js\"></script>")
    return layout("Inspector", body, user=user, active_tab="inspector")


def tools_page(user):
    body = ("<section class=\"card\"><h1>Tools</h1>"
            "<p id=\"t-scope\" class=\"muted\"></p>"
            "<h2>Macros the engine knows</h2>"
            "<ul id=\"t-macros\" class=\"roster\"></ul>"
            "<p id=\"t-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Expand macros</h2>"
            "<p>Expansion runs the engine's own macro road - the "
            "result below is the engine's answer, never a local "
            "re-implementation. Give a seed to make random macros "
            "reproducible.</p>"
            "<label>Text<input id=\"t-x-text\" class=\"entry-box\" "
            "placeholder=\"A line with {{char}} and {{user}} in it...\"></label>"
            "<div class=\"row\"><label>Character name"
            "<input id=\"t-x-char\" class=\"entry-box\"></label>"
            "<label>Your name<input id=\"t-x-user\" class=\"entry-box\" value=\"User\"></label>"
            "<label>Seed (optional)<input id=\"t-x-seed\" class=\"entry-box\"></label>"
            "<button id=\"t-expand\" class=\"btn\" type=\"button\">Expand macros</button></div>"
            "<pre id=\"t-x-out\" class=\"words\"></pre>"
            "<pre id=\"t-x-report\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Variables</h2>"
            "<p id=\"t-var-note\" class=\"muted\"></p>"
            "<ul id=\"t-vars\" class=\"roster\"></ul>"
            "<label>Text to resolve<input id=\"t-r-text\" class=\"entry-box\"></label>"
            "<div class=\"row\"><button id=\"t-resolve\" class=\"btn ghost\" "
            "type=\"button\">Resolve variables</button></div>"
            "<pre id=\"t-r-out\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Compose preview</h2>"
            "<p>Compose a prompt from parts, under a token budget, "
            "and see the messages it would send plus its token "
            "account - the engine composes; nothing is sent.</p>"
            "<label>System<textarea id=\"t-c-system\" class=\"entry-box\" "
            "rows=\"2\"></textarea></label>"
            "<label>Persona<textarea id=\"t-c-persona\" class=\"entry-box\" "
            "rows=\"2\"></textarea></label>"
            "<label>History (one line per line)"
            "<textarea id=\"t-c-history\" class=\"entry-box\" rows=\"3\"></textarea></label>"
            "<div class=\"row\"><label>Author's note"
            "<input id=\"t-c-note\" class=\"entry-box\"></label>"
            "<label>Note depth<input id=\"t-c-depth\" class=\"entry-box\" "
            "value=\"0\"></label>"
            "<label>Context limit<input id=\"t-c-limit\" class=\"entry-box\" "
            "value=\"4096\"></label>"
            "<label>Reserve for reply"
            "<input id=\"t-c-reserve\" class=\"entry-box\" value=\"512\"></label>"
            "<button id=\"t-compose\" class=\"btn\" type=\"button\">Compose</button></div>"
            "<pre id=\"t-c-out\" class=\"words\"></pre>"
            "<pre id=\"t-c-manifest\" class=\"words\"></pre>"
            "<p id=\"t-c-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/tools.js\"></script>")
    return layout("Tools", body, user=user, active_tab="tools")


def voice_page(user):
    body = ("<section class=\"card\"><h1>Voice</h1>"
            "<p>The engine's voice surface, as the desktop shows "
            "it: status, devices and their roles, the speech "
            "backends and their install truth, and voice "
            "sessions bound to chats.</p>"
            "<pre id=\"v-state\" class=\"words\"></pre>"
            "<pre id=\"v-status\" class=\"words\"></pre>"
            "<p id=\"v-provider-note\" class=\"muted\"></p>"
            "<p id=\"v-status-line\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Devices and roles</h2>"
            "<p>Provider: <span id=\"v-provider\"></span></p>"
            "<ul id=\"v-devices\" class=\"roster\"></ul>"
            "<ul id=\"v-roles\" class=\"roster\"></ul>"
            "<div class=\"row\"><label>Role<select id=\"v-role-pick\" class=\"entry-box\">"
            "</select></label><label>Device<select id=\"v-device-pick\" class=\"entry-box\">"
            "</select></label>"
            "<button id=\"v-assign\" class=\"btn\" type=\"button\">"
            "Assign role</button></div>"
            "<p id=\"v-role-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Speech backends</h2>"
            "<h3>Text to speech (speaking)</h3>"
            "<ul id=\"v-tts\" class=\"roster\"></ul>"
            "<h3>Speech to text (hearing)</h3>"
            "<ul id=\"v-stt\" class=\"roster\"></ul>"
            "<div class=\"row\"><label>Default speaking backend"
            "<select id=\"v-tts-default\" class=\"entry-box\"></select></label>"
            "<label>Default hearing backend"
            "<select id=\"v-stt-default\" class=\"entry-box\"></select></label>"
            "<button id=\"v-save-defaults\" class=\"btn\" type=\"button\">"
            "Save defaults</button></div>"
            "<p id=\"v-backend-status\" class=\"muted\"></p>"
            "<p id=\"v-synth-note\" class=\"muted\"></p>"
            "<p id=\"v-transcribe-note\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Voice sessions</h2>"
            "<p id=\"v-char-note\" class=\"muted\"></p>"
            "<div class=\"row\"><label>Chat<select id=\"v-chat\" class=\"entry-box\">"
            "</select></label>"
            "<button id=\"v-start\" class=\"btn\" type=\"button\">"
            "Start a voice session</button></div>"
            "<ul id=\"v-sessions\" class=\"roster\"></ul>"
            "<pre id=\"v-session-words\" class=\"words\"></pre>"
            "<pre id=\"v-latency\" class=\"words\"></pre>"
            "<div class=\"row\">"
            "<button id=\"v-live-start\" class=\"btn\" type=\"button\">"
            "Go live</button>"
            "<button id=\"v-live-stop\" class=\"btn ghost\" type=\"button\">"
            "Stop live</button>"
            "<button id=\"v-stop\" class=\"btn ghost\" type=\"button\">"
            "Stop session</button></div>"
            "<p id=\"v-live-status\" class=\"muted\"></p>"
            "<label>Words to speak<input id=\"v-speak-text\" "
            "class=\"entry-box\" placeholder=\"Type what the voice "
            "should say...\"></label>"
            "<div class=\"row\">"
            "<button id=\"v-speak\" class=\"btn\" type=\"button\">"
            "Speak it (on the engine host)</button>"
            "<button id=\"v-interrupt\" class=\"btn ghost\" type=\"button\">"
            "Interrupt</button></div>"
            "<pre id=\"v-speak-out\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Hearing: transcripts</h2>"
            "<p>The engine transcribes inside a live session, from "
            "the engine host's microphone - there is no upload "
            "transcription road. When you hold a transcript (from "
            "a live session, or your own notes), record it on the "
            "session, then project the session into its chat: "
            "the turns land as chat messages.</p>"
            "<label>Transcript<textarea id=\"v-turn-transcript\" "
            "class=\"entry-box\" rows=\"3\"></textarea></label>"
            "<label>Reply (optional)<textarea id=\"v-turn-response\" "
            "class=\"entry-box\" rows=\"2\"></textarea></label>"
            "<div class=\"row\">"
            "<button id=\"v-record-turn\" class=\"btn\" type=\"button\">"
            "Record turn on the session</button>"
            "<button id=\"v-project\" class=\"btn ghost\" type=\"button\">"
            "Project session into its chat</button></div>"
            "<pre id=\"v-turn-out\" class=\"words\"></pre>"
            "<h3>Record or upload a clip</h3>"
            "<p id=\"v-mic-note\" class=\"muted\"></p>"
            "<div class=\"row\">"
            "<button id=\"v-mic-record\" class=\"btn\" type=\"button\">"
            "Record from the microphone</button>"
            "<button id=\"v-mic-stop\" class=\"btn ghost\" type=\"button\" "
            "hidden>Stop recording</button></div>"
            "<audio id=\"v-mic-player\" controls hidden></audio>"
            "<p><a id=\"v-mic-download\" hidden>Download the recording</a></p>"
            "<label>Or choose an audio file<input id=\"v-clip\" "
            "type=\"file\" accept=\"audio/*\"></label>"
            "<div class=\"row\">"
            "<button id=\"v-transcribe\" class=\"btn\" type=\"button\">"
            "Ask the engine to transcribe it</button></div>"
            "<pre id=\"v-transcribe-out\" class=\"words\"></pre></section>"
            "<script src=\"/static/voice.js\"></script>")
    return layout("Voice", body, user=user, active_tab="voice")


def vision_page(user):
    body = ("<section class=\"card\"><h1>Vision</h1>"
            "<p>The engine's vision surface, as the desktop shows "
            "it: what can describe a picture (image facts only - "
            "no semantic caption provider exists), the pictures "
            "attached to a chat, and watch folders.</p>"
            "<pre id=\"s-providers\" class=\"words\"></pre>"
            "<p id=\"s-send-note\" class=\"muted\"></p>"
            "<p id=\"s-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>A chat's pictures</h2>"
            "<div class=\"row\"><label>Chat<select id=\"s-chat\" class=\"entry-box\">"
            "</select></label>"
            "<button id=\"s-load\" class=\"btn\" type=\"button\">"
            "Show the chat</button></div>"
            "<div id=\"s-transcript\"></div>"
            "<h3>Attachments</h3>"
            "<ul id=\"s-attachments\" class=\"roster\"></ul>"
            "<div id=\"s-thumbs\"></div></section>"
            "<section class=\"card\"><h2>Attach a picture</h2>"
            "<label>Picture<input id=\"s-file\" type=\"file\" "
            "accept=\"image/*\"></label>"
            "<label>Bind to a message (optional message id)"
            "<input id=\"s-message-id\" class=\"entry-box\"></label>"
            "<label>Describe it as image facts in the same step "
            "<input id=\"s-describe\" type=\"checkbox\"></label>"
            "<div class=\"row\">"
            "<button id=\"s-attach\" class=\"btn\" type=\"button\">"
            "Attach the picture</button></div>"
            "<p id=\"s-attach-status\" class=\"muted\"></p>"
            "<pre id=\"s-attach-out\" class=\"words\"></pre>"
            "<h3>Send words with a picture</h3>"
            "<label>Your message<input id=\"s-send-text\" "
            "class=\"entry-box\" placeholder=\"Words to send with "
            "the chosen picture...\"></label>"
            "<div class=\"row\">"
            "<button id=\"s-send\" class=\"btn\" type=\"button\">"
            "Send, with the picture attached</button></div>"
            "<pre id=\"s-send-out\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Describe a picture</h2>"
            "<p>Describing reports the image's facts from its "
            "bytes (format, size, dimensions, fingerprint) - "
            "never an invented caption.</p>"
            "<label>Attachment id<input id=\"s-desc-attach\" "
            "class=\"entry-box\"></label>"
            "<label>Question (optional)<input id=\"s-desc-q\" "
            "class=\"entry-box\"></label>"
            "<label>Ask for a semantic caption (refused plainly "
            "today: none exists)<input id=\"s-desc-semantic\" "
            "type=\"checkbox\"></label>"
            "<div class=\"row\">"
            "<button id=\"s-describe-btn\" class=\"btn\" type=\"button\">"
            "Describe</button></div>"
            "<pre id=\"s-desc-out\" class=\"words\"></pre>"
            "<h3>This chat's descriptions</h3>"
            "<ul id=\"s-descriptions\" class=\"roster\"></ul></section>"
            "<section class=\"card\"><h2>Watch folders</h2>"
            "<p>A watch folder's scans bring new pictures in the "
            "folder into the chat as attachments. The path is a "
            "folder on the engine host.</p>"
            "<ul id=\"s-watches\" class=\"roster\"></ul>"
            "<label>Folder path on the engine host"
            "<input id=\"s-watch-path\" class=\"entry-box\"></label>"
            "<label>Include subfolders <input id=\"s-watch-recursive\" "
            "type=\"checkbox\"></label>"
            "<div class=\"row\">"
            "<button id=\"s-watch-add\" class=\"btn\" type=\"button\">"
            "Watch this folder</button></div>"
            "<pre id=\"s-watch-out\" class=\"words\"></pre></section>"
            "<script src=\"/static/vision.js\"></script>")
    return layout("Vision", body, user=user, active_tab="vision")


def backups_page(user):
    body = ("<section class=\"card\"><h1>Backups</h1>"
            "<p>The engine's backup surface, as the desktop "
            "shows it: database backups and full bundles, "
            "created online while Rúnmál runs, and restore-"
            "staged - never applied.</p>"
            "<pre id=\"b-words\" class=\"words\"></pre>"
            "<ul id=\"b-list\" class=\"roster\"></ul>"
            "<div class=\"row\">"
            "<button id=\"b-create\" class=\"btn\" type=\"button\">"
            "Back up the database</button>"
            "<button id=\"b-create-full\" class=\"btn\" "
            "type=\"button\">Full backup (database + assets)"
            "</button></div>"
            "<p id=\"b-create-status\" class=\"muted\"></p>"
            "<pre id=\"b-created\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Stage a restore</h2>"
            "<p>Staging copies the backup to the restore area "
            "and verifies the copy. The live installation is "
            "not touched - staging only proves the backup can "
            "be restored.</p>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"b-stage-confirm\"> I understand staging "
            "verifies a copy and does not restore anything "
            "over the live data</label>"
            "<div class=\"row\">"
            "<button id=\"b-stage\" class=\"btn\" type=\"button\">"
            "Stage restore of the selected backup</button>"
            "<button id=\"b-stage-full\" class=\"btn ghost\" "
            "type=\"button\">Stage full restore</button></div>"
            "<pre id=\"b-stage-out\" class=\"words\"></pre>"
            "<p id=\"b-stage-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Download</h2>"
            "<p id=\"b-download-note\" class=\"muted\"></p>"
            "<p><a id=\"b-download\" href=\"#\" hidden>"
            "Download the selected backup</a></p>"
            "<h2>What this page cannot do</h2>"
            "<p id=\"b-delete-note\" class=\"muted\"></p>"
            "<p id=\"b-restore-note\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Import an archive</h2>"
            "<p>Import a portable .runmal archive file (on "
            "the engine host) into a fresh staging directory. "
            "Importing alone does not restore anything over "
            "the live data.</p>"
            "<label>Archive path on the engine host"
            "<input id=\"b-import-path\" class=\"entry-box\"></label>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"b-import-confirm\"> I understand the archive "
            "is imported into staging only</label>"
            "<button id=\"b-import\" class=\"btn\" type=\"button\">"
            "Import archive</button>"
            "<pre id=\"b-import-out\" class=\"words\"></pre>"
            "<p id=\"b-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/backups.js\"></script>")
    return layout("Backups", body, user=user, active_tab="backups")


def plugins_page(user):
    body = ("<section class=\"card\"><h1>Plugins</h1>"
            "<p>The engine's plugin registry, as the desktop's "
            "Plugins dialog shows it: what each plugin is, "
            "what it declares, its permission card, and its "
            "failure record.</p>"
            "<pre id=\"p-manager\" class=\"words\"></pre>"
            "<pre id=\"p-words\" class=\"words\"></pre>"
            "<ul id=\"p-list\" class=\"roster\"></ul>"
            "<p id=\"p-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>Selected plugin</h2>"
            "<pre id=\"p-detail\" class=\"words\"></pre>"
            "<pre id=\"p-card\" class=\"words\"></pre>"
            "<p id=\"p-failure\" class=\"muted\"></p>"
            "<div class=\"row\">"
            "<button id=\"p-enable\" class=\"btn\" type=\"button\">"
            "Enable</button>"
            "<button id=\"p-disable\" class=\"btn ghost\" "
            "type=\"button\">Disable</button>"
            "<button id=\"p-ack\" class=\"btn ghost\" "
            "type=\"button\">Acknowledge</button></div>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"p-uninstall-confirm\"> I understand "
            "uninstalling removes this plugin and its "
            "settings, with no undo</label>"
            "<button id=\"p-uninstall\" class=\"btn ghost\" "
            "type=\"button\">Uninstall</button>"
            "<pre id=\"p-action-out\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Plugin settings</h2>"
            "<p>The selected plugin's declared settings, "
            "through the engine's own validated road - a "
            "refused save writes nothing, and the engine's "
            "refusal words are shown as they come.</p>"
            "<div id=\"p-settings\"></div>"
            "<p id=\"p-settings-status\" class=\"muted\"></p>"
            "<div class=\"row\">"
            "<button id=\"p-settings-save\" class=\"btn\" "
            "type=\"button\">Save settings</button>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"p-settings-del-confirm\"> Confirm deleting "
            "the stored settings</label>"
            "<button id=\"p-settings-del\" class=\"btn ghost\" "
            "type=\"button\">Delete stored settings</button>"
            "</div></section>"
            "<section class=\"card\"><h2>Install a plugin pack</h2>"
            "<p>Plugins arrive as local packs - nothing is "
            "fetched from anywhere. Paste a pack envelope, "
            "or name a pack file on the engine host. Preview "
            "shows the permission card and writes nothing; "
            "installing grants exactly the permissions the "
            "pack's own manifest declares.</p>"
            "<label>Pack envelope (JSON)<textarea "
            "id=\"p-pack\" class=\"entry-box\" rows=\"5\">"
            "</textarea></label>"
            "<label>Or pack file path on the engine host"
            "<input id=\"p-pack-path\" class=\"entry-box\"></label>"
            "<div class=\"row\">"
            "<button id=\"p-preview\" class=\"btn ghost\" "
            "type=\"button\">Preview install</button>"
            "<button id=\"p-install\" class=\"btn\" "
            "type=\"button\">Install</button>"
            "<button id=\"p-update\" class=\"btn ghost\" "
            "type=\"button\">Update selected with this pack"
            "</button></div>"
            "<pre id=\"p-install-out\" class=\"words\"></pre></section>"
            "<section class=\"card\"><h2>Failure reports</h2>"
            "<ul id=\"p-failures\" class=\"roster\"></ul>"
            "<h2>Also on this router</h2>"
            "<p id=\"p-citizen-note\" class=\"muted\"></p>"
            "<h3>Quick replies</h3>"
            "<ul id=\"p-qr\" class=\"roster\"></ul>"
            "<h3>Expression sets</h3>"
            "<ul id=\"p-expr\" class=\"roster\"></ul></section>"
            "<script src=\"/static/plugins.js\"></script>")
    return layout("Plugins", body, user=user, active_tab="plugins")


def bridge_page(user):
    body = ("<section class=\"card\"><h1>Bridge</h1>"
            "<p>The engine's bridge credentials, as the "
            "desktop's Bridge dialog manages them: a "
            "credential lets an external bridge act with "
            "exactly the scopes it is granted.</p>"
            "<pre id=\"br-words\" class=\"words\"></pre>"
            "<ul id=\"br-list\" class=\"roster\"></ul>"
            "<p id=\"br-w10\" class=\"muted\"></p>"
            "<p id=\"br-status\" class=\"muted\"></p></section>"
            "<section class=\"card\"><h2>New credential</h2>"
            "<label>Label<input id=\"br-name\" "
            "class=\"entry-box\"></label>"
            "<label>Scopes (comma-separated, e.g. "
            "chat:read:*, chat:write:*, tts:request)"
            "<input id=\"br-scopes\" class=\"entry-box\"></label>"
            "<button id=\"br-create\" class=\"btn\" "
            "type=\"button\">Create credential</button>"
            "<p id=\"br-token-note\" class=\"muted\"></p>"
            "<label>The one-time token - copy it now"
            "<input id=\"br-token\" readonly "
            "placeholder=\"A new token appears here, once.\" class=\"entry-box\">"
            "</label></section>"
            "<section class=\"card\"><h2>Revoke</h2>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"br-revoke-confirm\"> I understand revoking "
            "stops anything using the selected credential's "
            "token at once, with no undo</label>"
            "<button id=\"br-revoke\" class=\"btn ghost\" "
            "type=\"button\">Revoke selected credential</button>"
            "<pre id=\"br-revoke-out\" class=\"words\"></pre></section>"
            "<script src=\"/static/bridge.js\"></script>")
    return layout("Bridge", body, user=user, active_tab="bridge")


def appearance_page(user):
    body = ("<section class=\"card\"><h1>Appearance</h1>"
            "<p>How this face looks, as the desktop's "
            "Appearance dialog offers it: theme variant, "
            "ornament, text size, and reduced motion. "
            "Choosing applies at once and saves.</p>"
            "<p id=\"a-words\" class=\"muted\"></p>"
            "<label>Theme variant<select id=\"a-variant\" class=\"entry-box\">"
            "<option value=\"dark\">Dark - the void ladder</option>"
            "<option value=\"light\">Light - pale iron &amp; "
            "paper</option></select></label>"
            "<p class=\"muted\">Dark or Light: the same token "
            "ladder and accents in both; Light keeps the "
            "accent hues, deepened where they would fail "
            "contrast on pale surfaces.</p>"
            "<label>Ornament<select id=\"a-ornament\" class=\"entry-box\">"
            "<option value=\"quiet\">Quiet - single iron "
            "border</option>"
            "<option value=\"standard\">Standard - stepped "
            "double-border frames</option>"
            "<option value=\"ceremonial\">Ceremonial - double "
            "frames, accent-tipped headers</option>"
            "</select></label>"
            "<p class=\"muted\">How much frame decoration "
            "panels carry. Content stays calm at every level "
            "- ornament lives on frames, never behind working "
            "text.</p>"
            "<label>Text size (%)<input id=\"a-scale\" "
            "type=\"number\" min=\"100\" max=\"200\" step=\"5\" class=\"entry-box\">"
            "</label>"
            "<p class=\"muted\">Scales the text of this face "
            "from 100% to 200%.</p>"
            "<label class=\"check\"><input type=\"checkbox\" "
            "id=\"a-motion\"> Reduced motion - cut animation "
            "durations to zero</label>"
            "<div class=\"row\">"
            "<button id=\"a-apply\" class=\"btn\" "
            "type=\"button\">Apply and save</button>"
            "<button id=\"a-reset\" class=\"btn ghost\" "
            "type=\"button\">Back to the house theme</button>"
            "</div>"
            "<p id=\"a-note\" class=\"muted\"></p>"
            "<p id=\"a-status\" class=\"muted\"></p></section>"
            "<script src=\"/static/appearance.js\"></script>")
    return layout("Appearance", body, user=user, active_tab="appearance")

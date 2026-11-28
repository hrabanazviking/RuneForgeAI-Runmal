"""W-09 compositions: Backups + Plugins + Library Search +
Bridge tabs, and the webface-local Appearance settings - the
last feature slice of the Rúnmál Web Access campaign.

All over EXISTING engine roads (no new engine routes):

BACKUPS - the desktop Backups dialog's surface (backups/
router.py, S114 + S802): POST /backups (online database
backup), GET /backups (the filesystem listing - database
backups only, by the engine's own filename law), POST
/backups/{name}/stage, POST /backups/full (database + assets
in one sealed ZIP), POST /backups/full/{name}/stage, and
POST /archive/import (a portable .runmal archive into a
fresh staging directory). The words renderers are the
desktop's own (desktop/backups_logic.py), ported to the raw
payloads the webface carries, wording unchanged.

HONEST GAPS - no engine road exists, so nothing here
pretends otherwise:
- NO download road: the engine never serves backup bytes
over HTTP. This face is colocated with the engine by its
own deployment law (the on-demand pair on one host), so a
download reads the named file out of the engine's own
backups folder on this host, behind the webface session,
after the engine's own filename law has validated the
name. Where the webface does not know the engine's data
dir, the road answers so in plain words instead of
pretending.
- NO delete road: the engine has no road that deletes a
backup, so this tab offers none and says so. Backups are
removed, if ever, by the owner's own hand on the host.
- NO apply-restore road: restoring in the engine means
STAGING a verified copy; swapping a staged restore into
place is a separate, deliberate act outside every shell
surface (the desktop says the same). This tab stages -
with a confirmation that names exactly that - and never
applies. Nothing here can overwrite the live database.

PLUGINS - the desktop Plugins dialog's manager surface
(plugins/router.py, P-081/P-083/P-089/P-092/P-093/P-098/
P-099): GET /plugins + /plugins/manager, the detail +
permission-card + failure-report reads, install preview +
install, update, uninstall, enable / disable / acknowledge,
and the settings roads (GET settings-form, GET settings,
POST settings, POST settings/delete). The words renderers
are the desktop's own (desktop/plugin_logic.py), ported the
same way. The dialog's other two citizen stores - quick
replies and expression sets - are listed here in the
desktop's words; their editors are not carried by this
tab and the page says so. Plugin settings DO have roads,
so they are built: the generated form's fields drive the
editor, and saving goes through the engine's validated
road, whose refusal words surface verbatim.

LIBRARY SEARCH - the desktop Library Search dialog's
surface (desktop/library_search_logic.py, R-14): one query
fanned out to the search routes that REALLY exist -
GET /hub/unified-search (P-192, owner-wide: entry metadata
AND verified pack contents, merged by entry) always, and
GET /workspaces/unified-search (P-182, one chat's bound
folder) when a chat is named. Both are LITERAL substring
searches by the engines' own law: no fuzzy, semantic,
ranked or scored matching exists in either, and none is
faked here. Faces has NO search route (its routers are
presentation / roster / census only), so faces is never a
key in the results: an absent source is the honest answer.
Each hub hit carries a jump to the tab that owns its kind
(a lorebook pack to Lorebooks, a scenario pack to
Scenarios, a preset bundle to Generation, a prompt pack to
Library); a workspace hit jumps to its chat.

BRIDGE - the desktop Bridge dialog's surface (bridge/
router.py admin roads, S601): GET /bridge/credentials,
POST /bridge/credentials, POST
/bridge/credentials/{id}/revoke. INV-023 governs: a
created credential's token plaintext appears exactly once,
in the creation response this module hands back raw; it is
never stored by the webface, never logged, and never
rendered by any words function here (credential views
carry id / name / scopes / state only).
THE W-10 LINE: this page manages the ENGINE's bridge
credentials - the same surface the desktop's Bridge dialog
manages. Agent access to THIS WEB FACE (webface agent
accounts and their API tokens, password change, recovery
codes) is W-10 scope and lives on the Account tab, not
here; the page states the line in those words.

APPEARANCE - the desktop Appearance dialog's prefs
(desktop/theme.py, R-15): theme variant (dark / light),
ornament (quiet / standard / ceremonial), text scale
(1.0-2.0) and reduced motion. The desktop stores them
shell-locally in QSettings; the webface stores them
WEBFACE-LOCALLY per account in the webface store, so they
follow the account to every device - that is the point of
storing them server-side. They are applied by the shell
(layout) on every page. The webface stylesheet carries the
same Appendix B token names as the desktop theme, so the
light variant is the desktop's own LIGHT_TOKENS table
applied as token overrides - a real second theme carried
by the token file, not an invented one. There is no
density setting in either shell, and none is invented
here. "Back to the house theme" restores the desktop's
defaults (dark / standard / 100% / motion on).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from runmal.desktop.theme import (
    ORNAMENTS,
    VARIANTS,
    clamp_text_scale,
    tokens_for,
)

from .engine import EngineError

# ------------------------------------------------------------ notes

DOWNLOAD_ROAD_NOTE = (
    "The engine has no road that serves backup bytes over "
    "HTTP. This face runs beside the engine on the same "
    "host, so a download reads the file from the engine's "
    "own backups folder, after the engine's filename law "
    "has validated its name - signed-in accounts only, "
    "exactly as every other road here."
)

DELETE_ROAD_NOTE = (
    "The engine has no road that deletes a backup, so this "
    "page offers no delete. A backup is removed, if ever, "
    "by your own hand on the engine host."
)

RESTORE_ROAD_NOTE = (
    "There is no one-click restore, here or on the desktop: "
    "restoring means staging a verified copy, and swapping "
    "a staged copy into place is a separate, deliberate "
    "act outside this page. Staging never touches the live "
    "installation."
)

CITIZEN_STORES_NOTE = (
    "Quick replies and expression sets ride the same "
    "engine router as the plugin registry and are listed "
    "below in the desktop's words. Their editors are not "
    "carried by this tab: on the desktop they live in the "
    "Plugins dialog's own tabs, and this page does not "
    "pretend to replace them."
)

FACES_SEARCH_NOTE = (
    "Faces is not searched: the engine's faces routers are "
    "presentation, roster and census surfaces only - no "
    "faces road accepts a query, so no faces result is "
    "ever dressed up as a searched one."
)

LITERAL_SEARCH_NOTE = (
    "Both real searches are literal substring searches - "
    "the engines' own law. No fuzzy, semantic, ranked or "
    "scored matching exists in either, and none is faked "
    "here. An empty query is refused, never treated as "
    "match-everything."
)

WORKSPACE_SCOPE_NOTE = (
    "Workspace search is chat-scoped by the engine's own "
    "law - there is no owner-wide workspace search - so "
    "the workspaces source joins only when you name the "
    "chat whose bound folder is meant."
)

BRIDGE_W10_NOTE = (
    "This page manages the engine's bridge credentials - "
    "the same surface the desktop's Bridge dialog manages. "
    "Agent access to this web face itself (agent accounts "
    "and their API tokens, password change, recovery "
    "codes) arrives in W-10 and lives on the Account tab, "
    "not here."
)

BRIDGE_TOKEN_NOTE = (
    "A new credential's token is shown once, in the "
    "one-time field on this page - copy it now. It will "
    "not be shown again, and this face does not store it."
)

APPEARANCE_STORE_NOTE = (
    "Appearance choices are webface preferences: they are "
    "saved on the server, against your webface account, "
    "and restored at sign-in on any device. They change "
    "only how this face looks - engine data is untouched. "
    "The desktop keeps the same choices on its own machine "
    "(QSettings); the two stores are separate, as the two "
    "shells are."
)

HOUSE_THEME = {
    "variant": "dark",
    "ornament": "standard",
    "text_scale": 1.0,
    "reduced_motion": False,
}

# ------------------------------------------- backups words
# Ported from runmal.desktop.backups_logic (R-14), unchanged
# in wording; inputs are the raw engine payloads.

_BACKUP_NAME_RE = re.compile(r"^runmal-backup-\d{8}T\d{6}\.db$")
_FULL_BACKUP_NAME_RE = re.compile(
    r"^runmal-full-backup-\d{8}T\d{6}\.zip$")


def _size_words(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} bytes"


def backup_kind(name: str) -> str:
    return "full" if str(name or "").startswith(
        "runmal-full-backup-") else "database"


def backup_line(view: dict) -> str:
    view = view if isinstance(view, dict) else {}
    bits = [
        "full backup" if backup_kind(view.get("name")) == "full"
        else "database backup",
        str(view.get("name") or "(unnamed)"),
    ]
    size = view.get("size_bytes")
    if isinstance(size, int) and size:
        bits.append(_size_words(size))
    if view.get("schema_revision"):
        bits.append(f"schema {view['schema_revision']}")
    if isinstance(view.get("asset_files"), int):
        bits.append(f"{view['asset_files']} asset file(s)")
    stamp = view.get("created_at") or view.get("modified_at")
    if stamp:
        bits.append(str(stamp))
    if view.get("secrets_included"):
        bits.append("WARNING: claims secrets included")
    return " · ".join(bits)


def backups_words(views: list) -> str:
    if not views:
        return (
            "No backups yet. A backup copies the live database "
            "safely while Rúnmál runs; a full backup bundles the "
            "database and the asset tree into one sealed file."
        )
    lines = [f"{len(views)} backup(s) on disk:"]
    lines.extend(f"- {backup_line(v)}" for v in views)
    return "\n".join(lines)


def stage_words(result: dict) -> str:
    if not result:
        return "Staging returned nothing."
    lines: list[str] = []
    if "bundle" in result or "staged_db" in result:
        ok = bool(result.get("ok"))
        lines.append(
            "Full backup staged and verified."
            if ok
            else "Full backup staging did not pass."
        )
        staged_db = result.get("staged_db")
        if staged_db:
            lines.append(f"Staged database: {staged_db}")
        staged_assets = result.get("staged_assets_dir")
        if staged_assets:
            lines.append(f"Staged assets: {staged_assets}")
        revision = result.get("schema_revision")
        if revision:
            lines.append(f"Schema revision: {revision}")
        counts = result.get("counts")
        if isinstance(counts, dict) and counts:
            counted = ", ".join(
                f"{k}: {counts[k]}" for k in sorted(counts)
            )
            lines.append(f"Contents: {counted}")
        checks = result.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                mark = "ok" if check.get("ok") else "FAILED"
                lines.append(
                    f"- check {check.get('name', '')}: {mark}"
                    f" — {check.get('detail', '')}"
                )
        warnings = result.get("warnings")
        if isinstance(warnings, list):
            lines.extend(
                f"Warning: {w}" for w in warnings if isinstance(w, str)
            )
    else:
        lines.append("Backup staged and verified.")
        name = result.get("name")
        if name:
            lines.append(f"Staged copy: {name}")
        path = result.get("path")
        if path:
            lines.append(f"At: {path}")
        revision = result.get("schema_revision")
        if revision:
            lines.append(f"Schema revision: {revision}")
    lines.append(
        "The live installation was not touched — staging only "
        "proves the backup can be restored."
    )
    return "\n".join(lines)


def archive_words(result: dict) -> str:
    """The archive-import report in words, from the report's
    own fields (the portable restore report document)."""
    result = result if isinstance(result, dict) else {}
    if not result:
        return "The import returned nothing."
    lines: list[str] = []
    ok = result.get("ok")
    if ok is True:
        lines.append("Archive imported into a fresh staging directory.")
    elif ok is False:
        lines.append("The archive import did not pass.")
    else:
        lines.append("Archive import report:")
    for key, label in (
            ("staging_dir", "Staged at"), ("directory", "Staged at"),
            ("format", "Format"), ("kind", "Kind")):
        if result.get(key):
            lines.append(f"{label}: {result[key]}")
    counts = result.get("counts")
    if isinstance(counts, dict) and counts:
        lines.append("Contents: " + ", ".join(
            f"{k}: {counts[k]}" for k in sorted(counts)))
    for key in ("warnings", "notes"):
        rows = result.get(key)
        if isinstance(rows, list):
            lines.extend(
                f"Warning: {w}" for w in rows if isinstance(w, str))
    lines.append(
        "Importing alone does not restore anything over the "
        "live data.")
    return "\n".join(lines)

# ------------------------------------------- backups roads


def _backup_notes() -> dict:
    return {
        "download": DOWNLOAD_ROAD_NOTE,
        "delete": DELETE_ROAD_NOTE,
        "restore": RESTORE_ROAD_NOTE,
    }


def list_backups(engine) -> dict:
    rows = engine.request("GET", "/api/v1/backups")
    rows = rows if isinstance(rows, list) else []
    views = [
        {**row, "kind": backup_kind(row.get("name")),
         "line": backup_line(row)}
        for row in rows if isinstance(row, dict)
    ]
    return {
        "backups": views,
        "words": backups_words(views),
        "notes": _backup_notes(),
    }


def create_backup(engine, full: bool) -> dict:
    road = "/api/v1/backups/full" if full else "/api/v1/backups"
    payload = engine.request("POST", road)
    payload = payload if isinstance(payload, dict) else {}
    view = {**payload, "kind": backup_kind(payload.get("name"))}
    return {
        "backup": view,
        "line": backup_line(view),
        "words": (
            f"Created: {backup_line(view)}\n"
            "The backup was verified by the engine before it "
            "reported success, and it holds no secrets "
            "(secrets_included is always false)."),
        "notes": _backup_notes(),
    }


def _validate_backup_name(name: str, full: bool) -> str:
    pattern = _FULL_BACKUP_NAME_RE if full else _BACKUP_NAME_RE
    if not pattern.match(name or ""):
        kind = "full backup" if full else "database backup"
        raise EngineError(
            f"not a Rúnmál {kind} filename: {name!r}", status=400)
    return name


def stage_backup(engine, name: str, full: bool) -> dict:
    name = _validate_backup_name(str(name or ""), full)
    road = (f"/api/v1/backups/full/{name}/stage" if full
            else f"/api/v1/backups/{name}/stage")
    payload = engine.request("POST", road)
    payload = payload if isinstance(payload, dict) else {}
    return {"report": payload, "words": stage_words(payload)}


def backup_download(engine, name: str) -> tuple[bytes, str]:
    """The named backup's bytes, read from the engine's own
    backups folder on this host (see the module docstring:
    no engine HTTP road serves backup bytes). The name must
    pass the engine's own filename law for either backup
    kind, and the resolved path must stay inside the
    backups folder."""
    name = str(name or "")
    if not (_BACKUP_NAME_RE.match(name) or _FULL_BACKUP_NAME_RE.match(name)):
        raise EngineError(
            f"not a Rúnmál backup filename: {name!r}", status=400)
    data_dir = getattr(engine, "data_dir", None)
    if not data_dir:
        raise EngineError(
            "Downloads read the backup from the engine's own "
            "backups folder on this host, and this webface "
            "was not started with the engine's data dir - so "
            "there is no honest download road here. The "
            "backup itself is safe on the engine host.",
            status=501)
    folder = (Path(data_dir) / "backups").resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise EngineError("backup not found", status=404)
    return path.read_bytes(), name


def import_archive(engine, path: str, confirm: bool) -> dict:
    if confirm is not True:
        raise EngineError(
            "Importing an archive needs its confirmation: the "
            "archive is imported into a fresh staging "
            "directory under the backup store's custody. "
            "Importing alone does not restore anything over "
            "the live data.", status=422)
    path = str(path or "").strip()
    if not path:
        raise EngineError(
            "name the archive file on the engine host first",
            status=422)
    payload = engine.request(
        "POST", "/api/v1/archive/import", json_body={"path": path})
    payload = payload if isinstance(payload, dict) else {}
    return {"report": payload, "words": archive_words(payload)}

# -------------------------------------------- plugins words
# Ported from runmal.desktop.plugin_logic (R-14), unchanged
# in wording; inputs are the raw engine payloads.


def plugin_line(view: dict) -> str:
    view = view if isinstance(view, dict) else {}
    bits = [str(view.get("name") or view.get("id") or "plugin")]
    if view.get("version"):
        bits.append(f"v{view['version']}")
    bits.append(str(view.get("state") or "unknown state"))
    capabilities = view.get("capabilities")
    permissions = view.get("permissions")
    bits.append(
        f"{len(capabilities) if isinstance(capabilities, list) else 0} "
        f"capabilit(ies), "
        f"{len(permissions) if isinstance(permissions, list) else 0} "
        f"permission(s)")
    if view.get("consecutive_failures"):
        bits.append(
            f"{view['consecutive_failures']} consecutive failure(s)")
    last_error = view.get("last_error")
    if isinstance(last_error, dict) and last_error:
        bits.append(
            f"last error: {last_error.get('error_type', '')}")
    return " · ".join(bits)


def plugins_words(views: list) -> str:
    if not views:
        return (
            "No plugins are registered. Plugins arrive as "
            "local packs, installed below; nothing is fetched "
            "from anywhere.")
    lines = [f"{len(views)} plugin(s) registered:"]
    lines.extend(f"- {plugin_line(v)}" for v in views)
    return "\n".join(lines)


def plugin_detail_words(detail: dict) -> str:
    if not detail:
        return "No plugin selected."
    lines: list[str] = []
    name = detail.get("name") or detail.get("id") or "plugin"
    heading = str(name)
    if detail.get("version"):
        heading += f" · v{detail['version']}"
    if detail.get("state"):
        heading += f" · {detail['state']}"
    lines.append(heading)
    manifest = detail.get("manifest")
    if isinstance(manifest, dict):
        description = manifest.get("description")
        if description:
            lines.append(str(description))
        author = manifest.get("author")
        if author:
            lines.append(f"Author: {author}")
    capabilities = detail.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        lines.append(
            "Capabilities: " + ", ".join(str(c) for c in capabilities))
    permissions = detail.get("permissions")
    if isinstance(permissions, list) and permissions:
        lines.append(
            "Permissions: " + ", ".join(str(p) for p in permissions))
    reserved = detail.get("reserved_permissions")
    if isinstance(reserved, list) and reserved:
        lines.append(
            "Reserved (honoured by nothing in v1): "
            + ", ".join(str(p) for p in reserved))
    failures = detail.get("failure_log")
    if isinstance(failures, list):
        lines.append(f"Recorded failures: {len(failures)}")
        for failure in failures:
            if not isinstance(failure, dict):
                continue
            lines.append(
                f"- {failure.get('surface', '')}/"
                f"{failure.get('hook', '')}: "
                f"{failure.get('error_type', '')} at "
                f"{failure.get('at', '')}")
    return "\n".join(lines)


def permission_words(card: dict) -> str:
    if not card:
        return "No permission card."
    lines: list[str] = []
    name = card.get("name") or card.get("plugin_id") or "plugin"
    heading = f"Permissions for {name}"
    if card.get("version"):
        heading += f" v{card['version']}"
    lines.append(heading)
    description = card.get("description")
    if description:
        lines.append(str(description))
    if card.get("requires_grant"):
        lines.append(
            "Installing or updating proceeds only when the granted "
            "set equals the declared set exactly.")
    else:
        lines.append("This plugin declares no permissions to grant.")
    rows = card.get("permissions")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            line = f"- {row.get('name', '')}"
            if row.get("reserved"):
                line += " (RESERVED — grants nothing today)"
            granted = row.get("granted")
            if granted is True:
                line += " · granted"
            elif granted is False:
                line += " · not granted"
            effect = row.get("effect")
            if effect:
                line += f": {effect}"
            lines.append(line)
    capabilities = card.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        named = ", ".join(
            str(c.get("name", "")) for c in capabilities
            if isinstance(c, dict))
        if named:
            lines.append(f"Capabilities: {named}")
    changes = card.get("changes")
    if isinstance(changes, dict):
        lines.append(
            f"Update: v{changes.get('from_version', '')} → "
            f"v{changes.get('to_version', '')}")
        for key, label in (
            ("permissions_added", "permissions added"),
            ("permissions_removed", "permissions removed"),
            ("capabilities_added", "capabilities added"),
            ("capabilities_removed", "capabilities removed"),
        ):
            values = changes.get(key)
            if isinstance(values, list) and values:
                lines.append(
                    f"- {label}: {', '.join(str(v) for v in values)}")
    notes = card.get("notes")
    if isinstance(notes, list):
        lines.extend(
            f"Note: {n}" for n in notes if isinstance(n, str))
    return "\n".join(lines)


def failure_line(report: dict) -> str:
    report = report if isinstance(report, dict) else {}
    bits = [str(report.get("plugin_id") or "plugin")]
    if report.get("state"):
        bits.append(str(report["state"]))
    total = report.get("total_recorded")
    bits.append(
        f"{total if isinstance(total, int) else 0} recorded failure(s)")
    if report.get("consecutive_failures"):
        bits.append(f"{report['consecutive_failures']} in a row")
    if report.get("self_disabled"):
        bits.append("self-disabled")
    if report.get("plain"):
        bits.append(str(report["plain"]))
    return " · ".join(bits)


def manager_words(manager: dict) -> str:
    manager = manager if isinstance(manager, dict) else {}
    installed = manager.get("installed")
    installed = installed if isinstance(installed, list) else []
    problems = manager.get("rehydration_problems")
    problems = problems if isinstance(problems, list) else []
    lines = [f"Manager ledger: {len(installed)} pack-managed "
             f"plugin(s) installed."]
    for row in installed:
        if isinstance(row, dict):
            lines.append("- " + plugin_line(row) if row.get("name")
                         else f"- {row.get('plugin_id') or row.get('id') or 'plugin'}")
    if problems:
        lines.append(
            f"{len(problems)} rehydration problem(s) stand in "
            "the ledger.")
        for problem in problems:
            lines.append(f"- {problem}")
    return "\n".join(lines)


def quick_reply_line(view: dict) -> str:
    view = view if isinstance(view, dict) else {}
    steps = view.get("steps")
    bits = [str(view.get("name") or view.get("id") or "quick reply")]
    bits.append(f"scope: {view.get('scope') or 'user'}")
    if view.get("chat_id"):
        bits.append(f"chat {view['chat_id']}")
    bits.append(
        f"{len(steps) if isinstance(steps, list) else 0} step(s)")
    bits.append("enabled" if view.get("enabled", True) else "disabled")
    return " · ".join(bits)


def expression_set_line(view: dict) -> str:
    view = view if isinstance(view, dict) else {}
    entries = view.get("entries")
    entries = entries if isinstance(entries, list) else []
    bits = [f"character {view.get('character_id') or ''}"]
    bits.append(f"{len(entries)} expression(s)")
    names = [str(e.get("name")) for e in entries
             if isinstance(e, dict) and e.get("name")]
    if names:
        bits.append(", ".join(names))
    if view.get("default"):
        bits.append(f"default: {view['default']}")
    return " · ".join(bits)

# -------------------------------------------- plugins roads


def plugins_overview(engine) -> dict:
    manager = engine.request("GET", "/api/v1/plugins/manager")
    rows = engine.request("GET", "/api/v1/plugins")
    rows = rows if isinstance(rows, list) else []
    failures = engine.request("GET", "/api/v1/plugins/failure-reports")
    failures = failures if isinstance(failures, list) else []
    replies = engine.request("GET", "/api/v1/quick-replies")
    replies = replies if isinstance(replies, list) else []
    sets = engine.request("GET", "/api/v1/expressions/sets")
    sets = sets if isinstance(sets, list) else []
    views = [
        {**row, "line": plugin_line(row)}
        for row in rows if isinstance(row, dict)
    ]
    return {
        "manager": manager if isinstance(manager, dict) else {},
        "manager_words": manager_words(manager),
        "plugins": views,
        "words": plugins_words(views),
        "failures": [
            {**row, "line": failure_line(row)}
            for row in failures if isinstance(row, dict)
        ],
        "quick_replies": [
            {**row, "line": quick_reply_line(row)}
            for row in replies if isinstance(row, dict)
        ],
        "expression_sets": [
            {**row, "line": expression_set_line(row)}
            for row in sets if isinstance(row, dict)
        ],
        "citizen_note": CITIZEN_STORES_NOTE,
    }


def plugin_detail(engine, plugin_id: str) -> dict:
    detail = engine.request("GET", f"/api/v1/plugins/{plugin_id}")
    detail = detail if isinstance(detail, dict) else {}
    card = engine.request(
        "GET", f"/api/v1/plugins/{plugin_id}/permission-card")
    card = card if isinstance(card, dict) else {}
    failure = engine.request(
        "GET", f"/api/v1/plugins/{plugin_id}/failure-report")
    failure = failure if isinstance(failure, dict) else {}
    settings_form = None
    settings = None
    settings_error = ""
    try:
        settings_form = engine.request(
            "GET", f"/api/v1/plugins/{plugin_id}/settings-form")
    except EngineError as exc:
        settings_error = exc.message
    try:
        settings = engine.request(
            "GET", f"/api/v1/plugins/{plugin_id}/settings")
    except EngineError as exc:
        settings_error = settings_error or exc.message
    return {
        "detail": detail,
        "words": plugin_detail_words(detail),
        "card": card,
        "card_words": permission_words(card),
        "failure": failure,
        "failure_line": failure_line(failure),
        "settings_form": settings_form,
        "settings": settings,
        "settings_error": settings_error,
    }


def install_body(payload: dict, *, for_preview: bool = False) -> dict:
    """Resolve an install payload to the engine's body - the
    desktop flow's own law (PluginFlow._install_body): a
    ``pack`` envelope passes through (granting exactly the
    permissions its manifest declares when no grant set is
    given); a ``source`` / ``path`` names a pack envelope
    file on this host, which is read here; anything else is
    refused plainly."""
    payload = payload if isinstance(payload, dict) else {}
    if "pack" in payload:
        body = dict(payload)
        if for_preview:
            return {"pack": body["pack"]}
        if "granted_permissions" not in body:
            pack = body["pack"] if isinstance(body["pack"], dict) else {}
            manifest = pack.get("plugin", {})
            body["granted_permissions"] = list(
                manifest.get("permissions", [])
                if isinstance(manifest, dict) else [])
        return body
    source = payload.get("source") or payload.get("path")
    if not source:
        raise EngineError(
            "plugin install needs a pack: a 'pack' envelope "
            "or the path to a pack file", status=422)
    try:
        envelope = json.loads(Path(str(source)).read_text())
    except OSError as exc:
        raise EngineError(
            f"could not read the pack file {source}: {exc}",
            status=422) from exc
    except json.JSONDecodeError as exc:
        raise EngineError(
            f"the pack file {source} is not JSON: {exc}",
            status=422) from exc
    if not isinstance(envelope, dict) or "plugin" not in envelope:
        raise EngineError(
            f"the file {source} is not a plugin pack envelope",
            status=422)
    grants = payload.get("granted_permissions")
    if grants is None:
        grants = list(envelope["plugin"].get("permissions", []))
    if for_preview:
        return {"pack": envelope}
    body = {"pack": envelope, "granted_permissions": grants}
    if "enable" in payload:
        body["enable"] = bool(payload["enable"])
    return body


def install_preview(engine, payload: dict) -> dict:
    result = engine.request(
        "POST", "/api/v1/plugins/install/preview",
        json_body=install_body(payload, for_preview=True))
    result = result if isinstance(result, dict) else {}
    return {"card": result, "words": permission_words(result)}


def install_plugin(engine, payload: dict) -> dict:
    result = engine.request(
        "POST", "/api/v1/plugins/install",
        json_body=install_body(payload))
    result = result if isinstance(result, dict) else {}
    return {"outcome": result, "words": _outcome_words(result)}


def update_plugin(engine, plugin_id: str, payload: dict | None) -> dict:
    if not payload:
        raise EngineError(
            "plugin update requires the new pack payload "
            "({'pack': ..., 'granted_permissions': [...]})",
            status=422)
    result = engine.request(
        "POST", f"/api/v1/plugins/{plugin_id}/update",
        json_body=install_body(payload))
    result = result if isinstance(result, dict) else {}
    return {"outcome": result, "words": _outcome_words(result)}


def _outcome_words(result: dict) -> str:
    if not result:
        return "The engine returned nothing."
    lines: list[str] = []
    outcome = result.get("outcome")
    if outcome:
        lines.append(f"Outcome: {outcome}")
    plugin = result.get("plugin")
    if isinstance(plugin, dict):
        lines.append(plugin_detail_words(plugin))
    card = result.get("card")
    if isinstance(card, dict):
        lines.append(permission_words(card))
    if not lines:
        lines.append("Done.")
    return "\n".join(lines)


def plugin_action(engine, plugin_id: str, action: str) -> dict:
    if action not in ("enable", "disable", "acknowledge"):
        raise EngineError(f"no such plugin action: {action}", status=404)
    result = engine.request(
        "POST", f"/api/v1/plugins/{plugin_id}/{action}")
    result = result if isinstance(result, dict) else {}
    return {"detail": result, "words": plugin_detail_words(result)}


def uninstall_plugin(engine, plugin_id: str, confirm: bool) -> dict:
    if confirm is not True:
        raise EngineError(
            "Uninstalling removes this pack-managed plugin "
            "from the registry and the manager ledger. Its "
            "settings leave with it. Confirm the uninstall "
            "first - there is no undo road.", status=422)
    result = engine.request(
        "POST", f"/api/v1/plugins/{plugin_id}/uninstall")
    result = result if isinstance(result, dict) else {}
    return {"outcome": result, "words": _outcome_words(result)}


def save_plugin_settings(engine, plugin_id: str, values) -> dict:
    if not isinstance(values, dict):
        raise EngineError(
            "settings must be a 'values' object", status=422)
    result = engine.request(
        "POST", f"/api/v1/plugins/{plugin_id}/settings",
        json_body={"values": values})
    result = result if isinstance(result, dict) else {}
    return {"settings": result}


def delete_plugin_settings(engine, plugin_id: str, confirm: bool) -> dict:
    if confirm is not True:
        raise EngineError(
            "Deleting a plugin's stored settings needs its "
            "confirmation: exactly this plugin's stored "
            "values go; its declared defaults remain.",
            status=422)
    result = engine.request(
        "POST", f"/api/v1/plugins/{plugin_id}/settings/delete",
        json_body={"confirm": True})
    result = result if isinstance(result, dict) else {}
    return {"result": result}

# --------------------------------------------- search words
# Ported from runmal.desktop.library_search_logic (R-14),
# unchanged in wording; inputs are the raw engine payloads.

SOURCES = ("hub", "workspaces")

_HUB_JUMPS = {
    "lorebook_pack": ("lorebooks", "Open the Lorebooks tab"),
    "scenario_pack": ("scenarios", "Open the Scenarios tab"),
    "preset_bundle": ("generation", "Open the Generation tab"),
    "prompt_pack": ("library", "Open the Library tab"),
}


def hit_line(source: str, hit: dict) -> str:
    hit = hit if isinstance(hit, dict) else {}
    title = hit.get("title") or hit.get("name") or hit.get("id")
    bits = [str(title or "(unnamed)")]
    if hit.get("kind"):
        bits.append(str(hit["kind"]))
    if hit.get("matched_by"):
        bits.append(f"matched by {hit['matched_by']}")
    occurrences = hit.get("occurrences")
    if isinstance(occurrences, int) and occurrences:
        bits.append(f"{occurrences} occurrence(s)")
    locator = hit.get("locator") or hit.get("path")
    if locator and source != "hub":
        bits.append(str(locator))
    line = " · ".join(bits)
    excerpt = hit.get("excerpt")
    if isinstance(excerpt, str) and excerpt:
        excerpt = " ".join(excerpt.split())
        if len(excerpt) > 80:
            excerpt = excerpt[:79] + "…"
        line += f" — {excerpt}"
    return line


def results_words(results: dict) -> str:
    if not results:
        return "No library sources were searched."
    lines: list[str] = []
    total = 0
    for source in SOURCES:
        if source not in results:
            continue
        hits = results[source]
        total += len(hits)
        lines.append(f"{source}: {len(hits)} hit(s)")
        lines.extend(f"- {hit_line(source, h)}" for h in hits)
    if total == 0:
        lines.append("No matches in the searched sources.")
    return "\n".join(lines)


def _hub_hit(row: dict) -> dict:
    tab, label = _HUB_JUMPS.get(
        str(row.get("kind") or ""), ("library", "Open the Library tab"))
    return {
        **row,
        "line": hit_line("hub", row),
        "jump": {"tab": tab, "label": label,
                 "id": str(row.get("id") or "")},
    }


def _workspace_hit(row: dict, chat_id: str) -> dict:
    return {
        **row,
        "line": hit_line("workspaces", row),
        "jump": {"tab": "chat", "label": "Open the chat",
                 "id": chat_id},
    }


def search_library(engine, query: str, chat_id: str = "",
                   kind: str = "") -> dict:
    """The R-14 fan-out over the webface's engine client:
    hub always, workspaces when a chat is named, faces
    never (no road). Result hits carry their raw rows plus
    the desktop's line and a jump to the owning tab."""
    query = str(query or "").strip()
    if not query:
        raise EngineError(
            "type a query first — an empty search is refused "
            "by both engines, never treated as "
            "match-everything", status=422)
    params: dict[str, Any] = {"q": query}
    if kind:
        params["kind"] = kind
    hub_doc = engine.request(
        "GET", "/api/v1/hub/unified-search", params=params)
    hub_doc = hub_doc if isinstance(hub_doc, dict) else {}
    hub_rows = hub_doc.get("matches")
    hub_hits = [
        _hub_hit(row) for row in hub_rows if isinstance(row, dict)
    ] if isinstance(hub_rows, list) else []
    sources: dict[str, Any] = {
        "hub": {"document": hub_doc, "hits": hub_hits},
    }
    word_sources: dict[str, list] = {"hub": hub_hits}
    if chat_id:
        ws_doc = engine.request(
            "GET", "/api/v1/workspaces/unified-search",
            params={"chat_id": chat_id, "q": query})
        ws_doc = ws_doc if isinstance(ws_doc, dict) else {}
        ws_rows = ws_doc.get("matches")
        ws_hits = [
            _workspace_hit(row, chat_id)
            for row in ws_rows if isinstance(row, dict)
        ] if isinstance(ws_rows, list) else []
        sources["workspaces"] = {"document": ws_doc, "hits": ws_hits}
        word_sources["workspaces"] = ws_hits
    return {
        "query": query,
        "sources": sources,
        "words": results_words(word_sources),
        "notes": {
            "faces": FACES_SEARCH_NOTE,
            "literal": LITERAL_SEARCH_NOTE,
            "workspace_scope": WORKSPACE_SCOPE_NOTE,
        },
    }

# --------------------------------------------- bridge words
# Ported from runmal.desktop.bridge_logic (R-14), unchanged
# in wording; inputs are the raw engine payloads. INV-023:
# no words function here ever sees a token - the list rows
# carry none, and the creation response is handed back raw,
# never rendered.


def credential_state(row: dict) -> str:
    return "revoked" if row.get("revoked_at") else "active"


def credential_line(view: dict) -> str:
    view = view if isinstance(view, dict) else {}
    bits = [str(view.get("name") or view.get("id") or "credential")]
    bits.append(credential_state(view))
    scopes = view.get("scopes")
    if isinstance(scopes, list) and scopes:
        bits.append("scopes: " + ", ".join(str(s) for s in scopes))
    else:
        bits.append("no scopes")
    if view.get("created_at"):
        bits.append(f"created {view['created_at']}")
    if view.get("last_used_at"):
        bits.append(f"last used {view['last_used_at']}")
    if view.get("revoked_at"):
        bits.append(f"revoked {view['revoked_at']}")
    return " · ".join(bits)


def bridge_status_words(credentials: list) -> str:
    if not credentials:
        return (
            "No bridge credentials. A credential lets an external "
            "bridge act with exactly the scopes it is granted; its "
            "token is shown once, at creation, and never again."
        )
    active = [c for c in credentials if credential_state(c) == "active"]
    revoked = [c for c in credentials if credential_state(c) == "revoked"]
    lines = [
        f"{len(credentials)} bridge credential(s): "
        f"{len(active)} active, {len(revoked)} revoked."
    ]
    scopes = sorted({
        str(s) for c in active
        for s in (c.get("scopes") if isinstance(c.get("scopes"), list)
                  else [])})
    if scopes:
        lines.append("Scopes in force: " + ", ".join(scopes))
    lines.extend(f"- {credential_line(c)}" for c in credentials)
    return "\n".join(lines)


def list_credentials(engine) -> dict:
    rows = engine.request("GET", "/api/v1/bridge/credentials")
    rows = rows if isinstance(rows, list) else []
    views = [
        {**row, "state": credential_state(row),
         "line": credential_line(row)}
        for row in rows if isinstance(row, dict)
    ]
    return {
        "credentials": views,
        "words": bridge_status_words(views),
        "notes": {"w10": BRIDGE_W10_NOTE, "token": BRIDGE_TOKEN_NOTE},
    }


def create_credential(engine, payload: dict) -> dict:
    """Create a credential and return the RAW creation
    result - token included, exactly as the engine answers.
    The caller (the browser page) shows the token once;
    this module retains nothing and renders nothing from
    it. The engine's body is ``name`` + ``scopes``; the
    page's form speaks of a label, so a ``label`` key is
    translated to ``name`` here when no name was given -
    the desktop flow's own translation."""
    body = dict(payload) if isinstance(payload, dict) else {}
    if "name" not in body and body.get("label"):
        body["name"] = body.pop("label")
    name = str(body.get("name") or "").strip()
    if not name:
        raise EngineError(
            "give the credential a label first", status=422)
    scopes = body.get("scopes")
    if isinstance(scopes, str):
        scopes = [part.strip() for part in scopes.split(",")
                  if part.strip()]
    if not isinstance(scopes, list) or not scopes:
        raise EngineError(
            "give the credential at least one scope - a "
            "credential acts with exactly the scopes it is "
            "granted (for example chat:read:*)", status=422)
    result = engine.request(
        "POST", "/api/v1/bridge/credentials",
        json_body={"name": name,
                   "scopes": [str(s) for s in scopes]})
    return result if isinstance(result, dict) else {}


def revoke_credential(engine, credential_id: str, confirm: bool) -> dict:
    if confirm is not True:
        raise EngineError(
            "Revoking a credential stops anything using its "
            "token at once, and there is no undo. Confirm "
            "the revocation first.", status=422)
    result = engine.request(
        "POST", f"/api/v1/bridge/credentials/{credential_id}/revoke")
    result = result if isinstance(result, dict) else {}
    view = {**result, "state": credential_state(result)}
    return {"credential": view, "line": credential_line(view)}

# ------------------------------------------------ appearance

_CSS_VAR_BY_TOKEN = (
    "void-000", "void-100", "panel", "panel-raised", "iron",
    "silver", "muted", "bifrost", "rune", "seidr", "forge",
    "aurora", "ember",
)


def normalize_appearance(data) -> dict:
    """Rebuild appearance prefs from a stored dict, falling
    back to the house theme for anything missing or unknown
    (the desktop's prefs_from_dict law: a corrupt stored
    value must never stop the shell from coming up themed)."""
    if not isinstance(data, dict):
        return dict(HOUSE_THEME)
    variant = data.get("variant")
    if variant not in VARIANTS:
        variant = HOUSE_THEME["variant"]
    ornament = data.get("ornament")
    if ornament not in ORNAMENTS:
        ornament = HOUSE_THEME["ornament"]
    try:
        text_scale = clamp_text_scale(float(data.get("text_scale", 1.0)))
    except (TypeError, ValueError):
        text_scale = HOUSE_THEME["text_scale"]
    return {
        "variant": variant,
        "ornament": ornament,
        "text_scale": text_scale,
        "reduced_motion": bool(data.get("reduced_motion", False)),
    }


def appearance_words(prefs: dict) -> str:
    prefs = normalize_appearance(prefs)
    return (
        f"{prefs['variant']} theme, {prefs['ornament']} ornament, "
        f"text at {round(prefs['text_scale'] * 100)}%, "
        f"reduced motion "
        f"{'on' if prefs['reduced_motion'] else 'off'}.")


def appearance_css(prefs: dict) -> str:
    """The shell overrides for one account's prefs, emitted
    by the layout on every page. The light variant is the
    desktop theme's own LIGHT_TOKENS applied over the
    stylesheet's token names; text scale rides the root
    font size (every font size in the sheet is in rem);
    ornament adjusts the chamfer + frame weight; reduced
    motion cuts transitions and animations to zero."""
    prefs = normalize_appearance(prefs)
    rules: list[str] = []
    if prefs["variant"] == "light":
        tokens = tokens_for("light")
        overrides = "; ".join(
            f"--{name}: {tokens[name]}" for name in _CSS_VAR_BY_TOKEN)
        rules.append(f":root {{ {overrides}; }}")
    if prefs["text_scale"] != 1.0:
        rules.append(
            f"html {{ font-size: {16 * prefs['text_scale']:.2f}px; }}")
    if prefs["ornament"] == "quiet":
        rules.append(
            ":root { --chamfer: polygon(3px 0, 100% 0, "
            "100% calc(100% - 3px), calc(100% - 3px) 100%, "
            "0 100%, 0 3px); }")
    elif prefs["ornament"] == "ceremonial":
        rules.append(
            ":root { --chamfer: polygon(16px 0, 100% 0, "
            "100% calc(100% - 16px), calc(100% - 16px) 100%, "
            "0 100%, 0 16px); } "
            ".card { box-shadow: inset 0 0 0 1px var(--iron); }")
    if prefs["reduced_motion"]:
        rules.append(
            "* { transition: none !important; "
            "animation: none !important; "
            "scroll-behavior: auto !important; }")
    return "\n".join(rules)


def get_appearance(store, user_id: int) -> dict:
    raw = store.get_appearance(user_id)
    return normalize_appearance(raw)


def set_appearance(store, user_id: int, data) -> dict:
    prefs = normalize_appearance(data)
    store.set_appearance(user_id, prefs)
    return prefs


def reset_appearance(store, user_id: int) -> dict:
    prefs = dict(HOUSE_THEME)
    store.set_appearance(user_id, prefs)
    return prefs

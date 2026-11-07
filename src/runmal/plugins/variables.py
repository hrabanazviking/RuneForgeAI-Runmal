"""Variables & state plugin API (P-093): per-chat state.

Roadmap line: "Variables & state plugin API: per-chat
variables/flags (Part IX scenarios consume the same store)."

A first-class P-081 citizen carrying ONE shared, durable,
per-chat store of variables and flags. Plugins, the host,
Part IX scenarios and the P-055 macro road all read and
write through the service functions in this module -- there
is no plugin-private silo and no scenario-private store.
Provenance is honest on every entry: each value records
which writer kind (plugin / host / scenario / macro) and
which writer id wrote it, when it was created, when it last
changed, and a version counter of how many writes it has
taken. Nothing is written anonymously.

Namespacing (design section 2): a key is `name` or
`namespace:name`. A bare name from a plugin writer lands in
that plugin's own namespace; a bare name from any other
writer lands in `shared`. The `shared` namespace is the
documented collaboration surface -- a later write replaces
the value, and the entry's provenance and version say who
wrote last. A plugin writer addressing ANOTHER plugin's
namespace is refused outright: one plugin's keys are never
silently overwritten by another plugin.

Storage is the P-089 durable file idiom: one JSON document
per owner at ``data_dir()/chat_variables/<user_id>.json``,
written atomically (tmp sibling, chmod 0o600, replace). A
corrupt store raises :class:`ChatVariableError` and is
never silently reset. No migration: head stays 0041.

P-055 relation (design section 5): macro variables are
strings in a per-expansion working copy; this store is
typed scalars, durable per chat. :func:`load_macro_variables`
and :func:`apply_macro_variables` are the bridge between
the two roads, over the shared namespace only.

Sandbox stance (P-082): only v1 surface permissions are
declared (``chat.read``, ``ui.contribute``), so the derived
resource grant set is EMPTY. The service functions are
trusted host wiring -- in-tree code calling in-tree code --
not a plugin-API network surface; the module opens no
socket and imports no network client.

Wiring: :func:`register_plugin` only. ``build_registry`` /
``create_app`` are unchanged; HTTP routes ride the existing
plugins router. See docs/VARIABLES_STATE_API_2026-11-07.md.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.variables"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "chat-variables-panel"
STORE_SCHEMA = "runmal-p093-chat-variables-v1"
STORE_DIR_NAME = "chat_variables"
SHARED_NAMESPACE = "shared"
MAX_ENTRIES_PER_CHAT = 500
MAX_KEY_CHARS = 128
MAX_NAME_CHARS = 64
MAX_VALUE_CHARS = 4000
WRITER_KINDS = frozenset({"plugin", "host", "scenario", "macro"})
ENTRY_KINDS = frozenset({"variable", "flag"})
DECLARED_EVENTS = ("chat.created", "chat.deleted")
_ENTRY_FIELDS = frozenset(
    {"key", "namespace", "name", "kind", "value", "writer_kind",
     "writer_id", "created_at", "updated_at", "version"})
_ID_RE = re.compile(r"[0-9a-fA-F-]{1,64}")
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_NS_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class ChatVariableError(ValueError):
    """A key, value, writer or store refusal (house 422)."""


class ChatVariableNotFoundError(ChatVariableError):
    """The named entry does not exist in this chat."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool))


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ChatVariableError(f"invalid {what}: {value!r}")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ChatVariableError(f"invalid {what}: {value!r}") from None
    return value


def _check_writer(writer_kind, writer_id) -> tuple[str, str]:
    if writer_kind not in WRITER_KINDS:
        raise ChatVariableError(
            f"unknown writer_kind: {writer_kind!r}")
    if not isinstance(writer_id, str) or not writer_id.strip():
        raise ChatVariableError("writer_id must be a non-empty string")
    if len(writer_id) > MAX_KEY_CHARS:
        raise ChatVariableError("writer_id is too long")
    return writer_kind, writer_id


def resolve_key(key, writer_kind: str, writer_id: str) -> tuple[str, str, str]:
    """Resolve a caller key to (full_key, namespace, name).

    A bare name lands in the writer's own namespace for a
    plugin writer, else in `shared`. An explicit namespace
    naming another plugin is refused for plugin writers --
    one plugin's keys are never another's to overwrite.
    """
    if not isinstance(key, str) or not key.strip():
        raise ChatVariableError(f"invalid variable key: {key!r}")
    key = key.strip()
    if len(key) > MAX_KEY_CHARS:
        raise ChatVariableError(
            f"variable key exceeds {MAX_KEY_CHARS} chars")
    if ":" in key:
        namespace, _, name = key.partition(":")
        if not _NS_RE.fullmatch(namespace):
            raise ChatVariableError(
                f"invalid namespace in key: {key!r}")
        if not _NAME_RE.fullmatch(name) or ":" in name:
            raise ChatVariableError(f"invalid name in key: {key!r}")
    else:
        name = key
        if not _NAME_RE.fullmatch(name):
            raise ChatVariableError(f"invalid variable key: {key!r}")
        namespace = writer_id if writer_kind == "plugin" else SHARED_NAMESPACE
    if writer_kind == "plugin" and namespace not in (writer_id, SHARED_NAMESPACE):
        raise ChatVariableError(
            f"plugin {writer_id!r} may not write namespace "
            f"{namespace!r}: another plugin's keys are not "
            "yours to overwrite")
    return f"{namespace}:{name}", namespace, name


def _check_variable_value(value):
    """Variables hold JSON scalars only (design section 3)."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if len(value) > MAX_VALUE_CHARS:
            raise ChatVariableError(
                f"variable value exceeds {MAX_VALUE_CHARS} chars")
        return value
    if _is_int(value):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ChatVariableError("variable value must be finite")
        return value
    raise ChatVariableError(
        f"variable values are JSON scalars, not {type(value).__name__}")


# -- Durable per-owner store (file idiom, no migration) ------------------


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    """The owner's store file under the data dir. The user
    id is validated as a UUID before it becomes a path."""
    _check_id(user_id, "user_id")
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{user_id}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "chats": {}}


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatVariableError(
            f"chat variable store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("chats"), dict):
        raise ChatVariableError("chat variable store has an unknown shape")
    return doc


def _save_doc(user_id: str, doc: dict, base_dir: Path | None = None) -> None:
    path = store_path(user_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _stored_entry(row) -> dict:
    """A stored entry re-validated on read: corrupt rows
    raise, never silently vanish from the owner's store."""
    if not isinstance(row, dict):
        raise ChatVariableError("stored entry is not an object")
    extra = set(row) - _ENTRY_FIELDS
    if extra:
        raise ChatVariableError(
            f"stored entry has unknown keys: {sorted(extra)}")
    kind = row.get("kind")
    if kind not in ENTRY_KINDS:
        raise ChatVariableError(f"stored entry has unknown kind: {kind!r}")
    if kind == "flag":
        if not isinstance(row.get("value"), bool):
            raise ChatVariableError("stored flag value is not a bool")
    else:
        _check_variable_value(row.get("value"))
    _check_writer(row.get("writer_kind"), row.get("writer_id"))
    if not _is_int(row.get("version")) or row["version"] < 1:
        raise ChatVariableError("stored entry has a bad version")
    return dict(row)


def _chat_entries(doc: dict, chat_id: str) -> dict:
    section = doc["chats"].get(chat_id)
    if section is None:
        return {}
    if not isinstance(section, dict) or not isinstance(section.get("entries"), dict):
        raise ChatVariableError("chat variable store has an unknown shape")
    return {key: _stored_entry(row)
            for key, row in section["entries"].items()}


def _write_entry(user_id, chat_id, full_key, namespace, name, kind,
                 value, writer_kind, writer_id, base_dir) -> dict:
    doc = _load_doc(user_id, base_dir)
    entries = _chat_entries(doc, chat_id)
    existing = entries.get(full_key)
    if existing is not None and existing["kind"] != kind:
        raise ChatVariableError(
            f"{full_key!r} already exists as a {existing['kind']}; "
            "kinds never blur -- unset it first")
    if existing is None and len(entries) >= MAX_ENTRIES_PER_CHAT:
        raise ChatVariableError(
            f"chat already holds {MAX_ENTRIES_PER_CHAT} entries")
    now = _now_iso()
    entry = {
        "key": full_key, "namespace": namespace, "name": name,
        "kind": kind, "value": value,
        "writer_kind": writer_kind, "writer_id": writer_id,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
        "version": (existing["version"] + 1) if existing else 1,
    }
    entries[full_key] = entry
    doc["chats"][chat_id] = {"entries": entries}
    _save_doc(user_id, doc, base_dir)
    return copy.deepcopy(entry)


# -- Service API: the one shared store ------------------------------------


def set_variable(user_id: str, chat_id: str, key, value, *,
                 writer_kind: str = "host", writer_id: str = "runmal.host",
                 base_dir: Path | None = None) -> dict:
    """Write one variable entry; returns the stored entry
    with its provenance. Overwriting a SHARED key replaces
    the value and says so in provenance + version; another
    plugin's namespace refuses (see resolve_key)."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    full_key, namespace, name = resolve_key(key, writer_kind, writer_id)
    value = _check_variable_value(value)
    return _write_entry(user_id, chat_id, full_key, namespace, name,
                        "variable", value, writer_kind, writer_id, base_dir)


def get_entry(user_id: str, chat_id: str, key, *,
              writer_kind: str = "host", writer_id: str = "runmal.host",
              base_dir: Path | None = None) -> dict | None:
    """The entry for a key, or None. Reads resolve keys
    through the reader's own namespace lens, like writes."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    full_key, _, _ = resolve_key(key, writer_kind, writer_id)
    doc = _load_doc(user_id, base_dir)
    entry = _chat_entries(doc, chat_id).get(full_key)
    return copy.deepcopy(entry) if entry is not None else None


def get_variable(user_id: str, chat_id: str, key, **kwargs):
    """The variable's value. A missing variable raises
    ChatVariableNotFoundError -- a typo never reads as a value;
    a flag under this key refuses on kind mismatch."""
    entry = get_entry(user_id, chat_id, key, **kwargs)
    if entry is None:
        raise ChatVariableNotFoundError(f"no variable named {key!r} in this chat")
    if entry["kind"] != "variable":
        raise ChatVariableError(
            f"{entry['key']!r} is a flag, not a variable")
    return entry["value"]


def set_flag(user_id: str, chat_id: str, key, value: bool, *,
             writer_kind: str = "host", writer_id: str = "runmal.host",
             base_dir: Path | None = None) -> dict:
    """Write one flag entry; flags hold bool ONLY."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    if not isinstance(value, bool):
        raise ChatVariableError(f"flag value must be a bool: {value!r}")
    full_key, namespace, name = resolve_key(key, writer_kind, writer_id)
    return _write_entry(user_id, chat_id, full_key, namespace, name,
                        "flag", value, writer_kind, writer_id, base_dir)


def get_flag(user_id: str, chat_id: str, key, **kwargs) -> bool:
    """A flag's value; a missing flag is honestly False.
    A variable under this key refuses on kind mismatch."""
    entry = get_entry(user_id, chat_id, key, **kwargs)
    if entry is None:
        return False
    if entry["kind"] != "flag":
        raise ChatVariableError(
            f"{entry['key']!r} is a variable, not a flag")
    return bool(entry["value"])


def increment_variable(user_id: str, chat_id: str, key, delta=1, *,
                       writer_kind: str = "host",
                       writer_id: str = "runmal.host",
                       base_dir: Path | None = None) -> dict:
    """addvar semantics: numeric add; a missing variable
    starts at 0. Bool current values and bool deltas refuse
    -- in this store a bool is a flag's truth, not a number."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    if not _is_number(delta):
        raise ChatVariableError(f"increment delta must be numeric: {delta!r}")
    full_key, namespace, name = resolve_key(key, writer_kind, writer_id)
    doc = _load_doc(user_id, base_dir)
    existing = _chat_entries(doc, chat_id).get(full_key)
    if existing is None:
        current = 0
    elif existing["kind"] != "variable":
        raise ChatVariableError(
            f"{full_key!r} is a flag, not a variable")
    elif not _is_number(existing["value"]):
        raise ChatVariableError(
            f"cannot increment non-numeric variable {full_key!r}")
    else:
        current = existing["value"]
    result = current + delta
    if isinstance(result, float) and not math.isfinite(result):
        raise ChatVariableError("increment result must be finite")
    return _write_entry(user_id, chat_id, full_key, namespace, name,
                        "variable", result, writer_kind, writer_id, base_dir)


def delete_variable(user_id: str, chat_id: str, key, *,
                    writer_kind: str = "host",
                    writer_id: str = "runmal.host",
                    base_dir: Path | None = None) -> bool:
    """Remove one entry (either kind). Returns False when
    the key was absent -- deletion never invents a victim.
    The namespace refusal applies to deletes too."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    full_key, _, _ = resolve_key(key, writer_kind, writer_id)
    doc = _load_doc(user_id, base_dir)
    entries = _chat_entries(doc, chat_id)
    if full_key not in entries:
        return False
    del entries[full_key]
    doc["chats"][chat_id] = {"entries": entries}
    _save_doc(user_id, doc, base_dir)
    return True


def list_entries(user_id: str, chat_id: str, *,
                 namespace: str | None = None, kind: str | None = None,
                 base_dir: Path | None = None) -> list[dict]:
    """One chat's entries with provenance, sorted by full
    key, optionally filtered by namespace and/or kind."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    if kind is not None and kind not in ENTRY_KINDS:
        raise ChatVariableError(f"unknown entry kind: {kind!r}")
    doc = _load_doc(user_id, base_dir)
    entries = _chat_entries(doc, chat_id)
    rows = [copy.deepcopy(entries[key]) for key in sorted(entries)]
    if namespace is not None:
        rows = [row for row in rows if row["namespace"] == namespace]
    if kind is not None:
        rows = [row for row in rows if row["kind"] == kind]
    return rows


def snapshot_chat(user_id: str, chat_id: str, *,
                  base_dir: Path | None = None) -> dict:
    """A deep copy of one chat's whole section: the
    inspectable state document for this chat."""
    return {"chat_id": _check_id(chat_id, "chat_id"),
            "entries": list_entries(user_id, chat_id, base_dir=base_dir)}


def clear_chat(user_id: str, chat_id: str, *,
               base_dir: Path | None = None) -> int:
    """Remove one chat's whole section; returns how many
    entries were removed. This explicit verb is the ONLY
    road that deletes durable per-chat state in bulk."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    doc = _load_doc(user_id, base_dir)
    entries = _chat_entries(doc, chat_id)
    if chat_id in doc["chats"]:
        del doc["chats"][chat_id]
        _save_doc(user_id, doc, base_dir)
    return len(entries)


def seed_variables(user_id: str, chat_id: str, mapping, *,
                   writer_kind: str = "scenario",
                   writer_id: str = "runmal.scenario",
                   base_dir: Path | None = None) -> list[str]:
    """Seed MISSING keys only (the Part IX contract): a
    scenario's initial_variables land in the shared store
    without ever overwriting live state. A value that is a
    bool seeds a flag; any other scalar seeds a variable.
    Returns the full keys actually seeded, in input order."""
    _check_id(user_id, "user_id")
    _check_id(chat_id, "chat_id")
    _check_writer(writer_kind, writer_id)
    if not isinstance(mapping, dict):
        raise ChatVariableError("seed mapping must be an object")
    seeded: list[str] = []
    for key, value in mapping.items():
        full_key, _, _ = resolve_key(key, writer_kind, writer_id)
        if get_entry(user_id, chat_id, full_key,
                     writer_kind=writer_kind, writer_id=writer_id,
                     base_dir=base_dir) is not None:
            continue
        if isinstance(value, bool):
            set_flag(user_id, chat_id, key, value,
                     writer_kind=writer_kind, writer_id=writer_id,
                     base_dir=base_dir)
        else:
            set_variable(user_id, chat_id, key, value,
                         writer_kind=writer_kind, writer_id=writer_id,
                         base_dir=base_dir)
        seeded.append(full_key)
    return seeded


# -- The P-055 macro bridge ------------------------------------------------


def _macro_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_macro_variables(user_id: str, chat_id: str, *,
                         base_dir: Path | None = None) -> dict:
    """The chat's SHARED variables as a P-055 macro map:
    string values only (a macro has no null, so None-valued
    entries are skipped, and flags -- a separate kind -- are
    not variables and never leak into the macro map).
    Plugin-namespaced entries stay plugin-private here: a
    macro is shared-surface text."""
    rows = list_entries(user_id, chat_id, namespace=SHARED_NAMESPACE,
                        kind="variable", base_dir=base_dir)
    out: dict[str, str] = {}
    for row in rows:
        text = _macro_string(row["value"])
        if text is not None:
            out[row["name"]] = text
    return out


def apply_macro_variables(user_id: str, chat_id: str, mapping, *,
                          base_dir: Path | None = None) -> list[dict]:
    """Persist a macro expansion report's variable map
    into the shared namespace, writer_kind=macro. Values
    stay the exact strings setvar left behind. Returns the
    stored entries, sorted by key."""
    if not isinstance(mapping, dict):
        raise ChatVariableError("macro variable map must be an object")
    written = []
    for name, value in mapping.items():
        if not isinstance(value, str):
            raise ChatVariableError(
                f"macro variable {name!r} is not a string: {value!r}")
        written.append(set_variable(
            user_id, chat_id, name, value, writer_kind="macro",
            writer_id="runmal.prompt.macros", base_dir=base_dir))
    return sorted(written, key=lambda row: row["key"])


# -- The P-081 citizen ------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Variables & State",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Per-chat variables and flags in one "
                       "shared, provenance-carrying store for "
                       "plugins, scenarios and prompt macros.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.sidebar",
                "label": "Chat Variables",
                "order": 100,
                "payload": {"kind": "panel", "route": "chat-variables"},
            }
        ],
        "settings": {"schema": {}, "defaults": {}},
        "enabled_by_default": False,
    }


def build_manifest():
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class VariablesPlugin:
    """The citizen: a UI contribution plus declared chat
    events whose handler abstains -- durable per-chat state
    is removed only by the explicit clear verb, never
    silently by an event (the P-089 stance)."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    @property
    def manifest(self):
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    async def on_event(self, event) -> None:
        return None


def register_plugin(registry: PluginRegistry, *,
                    base_dir: Path | None = None,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, VariablesPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = VariablesPlugin(base_dir)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS", "ENTRY_KINDS", "MAX_ENTRIES_PER_CHAT",
    "MAX_KEY_CHARS", "MAX_NAME_CHARS", "MAX_VALUE_CHARS",
    "PLUGIN_ID", "PLUGIN_VERSION", "SHARED_NAMESPACE",
    "STORE_DIR_NAME", "STORE_SCHEMA", "UI_LOCAL_ID", "VERSION",
    "WRITER_KINDS", "ChatVariableError", "ChatVariableNotFoundError",
    "VariablesPlugin", "apply_macro_variables", "build_manifest",
    "clear_chat", "delete_variable", "get_entry", "get_flag",
    "get_variable", "increment_variable", "list_entries",
    "load_macro_variables", "manifest_data", "register_plugin",
    "resolve_key", "sandbox_grants", "seed_variables",
    "set_flag", "set_variable", "snapshot_chat", "store_path",
]

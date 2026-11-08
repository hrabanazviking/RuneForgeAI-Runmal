"""Quick Replies plugin (P-089): user-defined one-tap macros.

Roadmap line: "Quick Replies: user-defined one-tap macros
incl. chained actions and input senders."

A first-class P-081 citizen carrying STORED, user-owned
quick-reply definitions plus their execution road. The line
this slice draws, from the code: P-055
(:mod:`runmal.prompt.macros`) is the one text-expansion
engine; a quick reply is a named, durable definition whose
steps expand through that engine and land through the app's
own chat road. No second macro engine exists here.

Definitions are durable per-user data in the P-076 / P-083
file idiom -- one JSON document at
``data_dir()/quick_replies/<user_id>.json``, written
atomically (tmp sibling, chmod 0o600, replace). A corrupt
store raises :class:`QuickReplyError` and is never silently
reset: user data is not wiped to hide damage. No migration:
head stays 0041.

Execution semantics (plain): steps run in declared order.
Each step's text expands via P-055 in STRICT mode, so an
unknown or malformed macro fails the step BEFORE anything is
appended for it -- raw ``{{...}}`` text is never posted as if
it were content. Variables thread across steps through the
expansion reports. Each successful step appends through
:func:`runmal.chats.service.append_message`, so the P-076
undo journal, the P-075 provenance document and the plugin
``message.created`` dispatch all apply per step, exactly as
for a hand-sent message. The first failure stops the chain:
applied steps stay applied (each was its own committed
append), the failure and the skipped remainder are recorded,
and the execution record is persisted and returned -- a
chain is never silently half-applied without a record.

Input-sender semantics (plain): a step with
``sender="input_sender"`` (user role only) lands as a USER
message -- in the transcript it is the user's own message,
exactly what a following generation call consumes,
indistinguishable in role and authorship from typed-and-sent
input. The P-075 receipt still tells the truth about the
road: origin kind ``manual`` (the closed P-075 vocabulary
has no quick-reply kind, and none is forged) with origin
facts ``via="quick_reply"``, the reply id/name, the step
index and ``sender`` naming the declared sender. A
``quick_reply``-sender step lands with its declared role
under the same receipt shape. Quick replies never call a
model themselves: no hidden generation.

Sandbox stance (P-082): only v1 surface permissions are
declared (``chat.read``, ``ui.contribute``; ``chat.write`` is
RESERVED and NOT declared), so the derived resource grant
set is EMPTY. Execution is trusted host wiring -- in-tree
code calling the chats service directly, the trust class of
P-084's ``session_factory`` -- not a plugin-API surface.

Wiring: :func:`register_plugin` only. ``build_registry`` /
``create_app`` are unchanged; CRUD + execute HTTP routes
ride the existing plugins router. See
docs/QUICK_REPLIES_2026-11-07.md.
"""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from runmal.auth import data_dir
from runmal.chats import provenance as prov_mod
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.prompt.macros import MacroContext, MacroError, expand_macros
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.quick-replies"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "quick-replies-panel"
STORE_SCHEMA = "runmal-p089-quick-replies-v1"
STORE_DIR_NAME = "quick_replies"
MAX_REPLIES_PER_USER = 200
MAX_STEPS = 8
MAX_NAME_CHARS = 120
MAX_TEXT_CHARS = 4000
MAX_EXECUTIONS_KEPT = 50
STEP_KINDS = frozenset({"message"})
STEP_ROLES = frozenset({"user", "assistant", "system"})
STEP_SENDERS = frozenset({"input_sender", "quick_reply"})
SCOPES = frozenset({"user", "chat"})
DECLARED_EVENTS = ("chat.created", "chat.deleted")
_STEP_FIELDS = frozenset({"kind", "role", "text", "sender"})
_REPLY_FIELDS = frozenset(
    {"id", "name", "text", "steps", "scope", "chat_id",
     "enabled", "created_at", "updated_at"})
_ID_RE = re.compile(r"[0-9a-fA-F-]{1,64}")


class QuickReplyError(ValueError):
    """A definition, store or execution refusal (house 422)."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise QuickReplyError(f"invalid {what}: {value!r}")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise QuickReplyError(f"invalid {what}: {value!r}") from None
    return value


def _check_name(value) -> str:
    if not isinstance(value, str):
        raise QuickReplyError(f"reply name must be a string: {value!r}")
    name = value.strip()
    if not 1 <= len(name) <= MAX_NAME_CHARS:
        raise QuickReplyError(
            f"reply name must be 1..{MAX_NAME_CHARS} chars")
    return name


def _check_text(value, what: str = "step text") -> str:
    if not isinstance(value, str):
        raise QuickReplyError(f"{what} must be a string: {value!r}")
    if not 1 <= len(value) <= MAX_TEXT_CHARS:
        raise QuickReplyError(
            f"{what} must be 1..{MAX_TEXT_CHARS} chars")
    if not value.strip():
        raise QuickReplyError(f"{what} must not be blank")
    return value


# -- Step / reply documents (strict *_from_data) -------------------------


def step_from_data(data, index: int = 0) -> dict:
    """One validated step document (strict keys, house style).

    Defaults: ``kind`` is ``message`` (the only v1 kind),
    ``role`` is ``user``, and ``sender`` is ``input_sender``
    for a user-role step, else ``quick_reply``. An explicit
    ``input_sender`` with a non-user role refuses: an input
    sender IS the user speaking, and any other pairing would
    forge the receipt.
    """
    if not isinstance(data, dict):
        raise QuickReplyError(f"step {index} must be an object")
    extra = set(data) - _STEP_FIELDS
    if extra:
        raise QuickReplyError(
            f"step {index} has unknown keys: {sorted(extra)}")
    kind = data.get("kind", "message")
    if kind not in STEP_KINDS:
        raise QuickReplyError(f"step {index} has unknown kind: {kind!r}")
    role = data.get("role", "user")
    if role not in STEP_ROLES:
        raise QuickReplyError(f"step {index} has unknown role: {role!r}")
    sender = data.get("sender")
    if sender is None:
        sender = "input_sender" if role == "user" else "quick_reply"
    if sender not in STEP_SENDERS:
        raise QuickReplyError(
            f"step {index} has unknown sender: {sender!r}")
    if sender == "input_sender" and role != "user":
        raise QuickReplyError(
            f"step {index}: input_sender requires role 'user'")
    return {
        "kind": kind,
        "role": role,
        "text": _check_text(data.get("text"), f"step {index} text"),
        "sender": sender,
    }


def step_to_data(step: dict) -> dict:
    return {
        "kind": step["kind"],
        "role": step["role"],
        "text": step["text"],
        "sender": step["sender"],
    }


def reply_from_data(data) -> dict:
    """A validated reply definition, minus id + timestamps.

    ``text`` is the one-tap shorthand for a single user-role
    input-sender step; ``text`` and ``steps`` together reject
    (one truth per definition).
    """
    if not isinstance(data, dict):
        raise QuickReplyError("reply must be an object")
    extra = set(data) - _REPLY_FIELDS
    if extra:
        raise QuickReplyError(f"reply has unknown keys: {sorted(extra)}")
    name = _check_name(data.get("name"))
    if "text" in data and data.get("text") is not None and "steps" in data \
            and data.get("steps") is not None:
        raise QuickReplyError("reply carries both 'text' and 'steps'")
    raw_steps = data.get("steps")
    if raw_steps is None:
        if data.get("text") is None:
            raise QuickReplyError("reply needs 'steps' or 'text'")
        raw_steps = [{"kind": "message", "role": "user",
                      "sender": "input_sender",
                      "text": data.get("text")}]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise QuickReplyError("reply steps must be a non-empty list")
    if len(raw_steps) > MAX_STEPS:
        raise QuickReplyError(f"reply has too many steps (max {MAX_STEPS})")
    steps = [step_from_data(row, i) for i, row in enumerate(raw_steps)]
    scope = data.get("scope", "user")
    if scope not in SCOPES:
        raise QuickReplyError(f"unknown reply scope: {scope!r}")
    chat_id = data.get("chat_id")
    if scope == "chat":
        chat_id = _check_id(chat_id, "chat_id")
    elif chat_id is not None:
        raise QuickReplyError("a user-scope reply must not name a chat_id")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise QuickReplyError(f"reply enabled must be a bool: {enabled!r}")
    return {
        "name": name,
        "steps": steps,
        "scope": scope,
        "chat_id": chat_id,
        "enabled": enabled,
    }


def reply_to_data(reply: dict) -> dict:
    return {
        "id": reply["id"],
        "name": reply["name"],
        "steps": [step_to_data(step) for step in reply["steps"]],
        "scope": reply["scope"],
        "chat_id": reply["chat_id"],
        "enabled": reply["enabled"],
        "created_at": reply["created_at"],
        "updated_at": reply["updated_at"],
    }


# -- Durable per-user store (file idiom, no migration) -------------------


def store_path(user_id: str, base_dir: Path | None = None) -> Path:
    """The owner's store file under the data dir. The user id
    is validated as a UUID before it ever becomes a path."""
    _check_id(user_id, "user_id")
    root = Path(base_dir) if base_dir is not None else data_dir()
    return root / STORE_DIR_NAME / f"{user_id}.json"


def _empty_doc() -> dict:
    return {"schema": STORE_SCHEMA, "replies": [], "executions": []}


def _load_doc(user_id: str, base_dir: Path | None = None) -> dict:
    path = store_path(user_id, base_dir)
    if not path.exists():
        return _empty_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuickReplyError(
            f"quick reply store is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != STORE_SCHEMA \
            or not isinstance(doc.get("replies"), list) \
            or not isinstance(doc.get("executions"), list):
        raise QuickReplyError("quick reply store has an unknown shape")
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


def _stored_reply(row) -> dict:
    """A stored row re-validated on read: corrupt rows raise,
    never silently vanish from the owner's library."""
    if not isinstance(row, dict):
        raise QuickReplyError("stored reply is not an object")
    body = reply_from_data(row)
    return {
        "id": _check_id(row.get("id"), "reply id"),
        **body,
        "created_at": row.get("created_at") or _now_iso(),
        "updated_at": row.get("updated_at") or _now_iso(),
    }


def _check_duplicate(doc: dict, body: dict, exclude_id: str | None) -> None:
    for row in doc["replies"]:
        other = _stored_reply(row)
        if exclude_id is not None and other["id"] == exclude_id:
            continue
        if other["name"] == body["name"] and other["scope"] == body["scope"] \
                and other["chat_id"] == body["chat_id"]:
            raise QuickReplyError(
                f"a quick reply named {body['name']!r} already exists "
                "in this scope")


# -- CRUD (owner-scoped service API) --------------------------------------


def create_reply(user_id: str, data, *, base_dir: Path | None = None) -> dict:
    body = reply_from_data(data)
    doc = _load_doc(user_id, base_dir)
    if len(doc["replies"]) >= MAX_REPLIES_PER_USER:
        raise QuickReplyError(
            f"quick reply limit reached ({MAX_REPLIES_PER_USER})")
    _check_duplicate(doc, body, None)
    now = _now_iso()
    reply = {"id": str(uuid.uuid4()), **body,
             "created_at": now, "updated_at": now}
    doc["replies"].append(reply_to_data(reply))
    _save_doc(user_id, doc, base_dir)
    return reply_to_data(reply)


def list_replies(user_id: str, *, chat_id: str | None = None,
                 base_dir: Path | None = None) -> list[dict]:
    """The owner's replies: every user-scope reply, plus the
    chat-scope replies bound to ``chat_id`` when one is named.
    Sorted by name for a stable one-tap surface."""
    doc = _load_doc(user_id, base_dir)
    out = []
    for row in doc["replies"]:
        reply = _stored_reply(row)
        if reply["scope"] == "chat" and reply["chat_id"] != chat_id:
            continue
        out.append(reply_to_data(reply))
    out.sort(key=lambda r: (r["name"].lower(), r["id"]))
    return out


def get_reply(user_id: str, reply_id: str,
              *, base_dir: Path | None = None) -> dict | None:
    _check_id(reply_id, "reply id")
    doc = _load_doc(user_id, base_dir)
    for row in doc["replies"]:
        reply = _stored_reply(row)
        if reply["id"] == reply_id:
            return reply_to_data(reply)
    return None


def update_reply(user_id: str, reply_id: str, data,
                 *, base_dir: Path | None = None) -> dict | None:
    """Full replace of the editable fields; id + created_at
    are preserved. ``None`` when the reply is not the owner's."""
    _check_id(reply_id, "reply id")
    body = reply_from_data(data)
    doc = _load_doc(user_id, base_dir)
    for index, row in enumerate(doc["replies"]):
        reply = _stored_reply(row)
        if reply["id"] != reply_id:
            continue
        _check_duplicate(doc, body, reply_id)
        updated = {"id": reply_id, **body,
                   "created_at": reply["created_at"],
                   "updated_at": _now_iso()}
        doc["replies"][index] = reply_to_data(updated)
        _save_doc(user_id, doc, base_dir)
        return reply_to_data(updated)
    return None


def delete_reply(user_id: str, reply_id: str,
                 *, base_dir: Path | None = None) -> bool:
    _check_id(reply_id, "reply id")
    doc = _load_doc(user_id, base_dir)
    kept = [row for row in doc["replies"]
            if not (isinstance(row, dict) and row.get("id") == reply_id)]
    if len(kept) == len(doc["replies"]):
        return False
    doc["replies"] = kept
    _save_doc(user_id, doc, base_dir)
    return True


def list_executions(user_id: str, *, base_dir: Path | None = None) -> list[dict]:
    """Persisted execution records, newest first."""
    doc = _load_doc(user_id, base_dir)
    return [copy.deepcopy(row) for row in reversed(doc["executions"])]


def _record_execution(user_id: str, record: dict,
                      base_dir: Path | None = None) -> dict:
    doc = _load_doc(user_id, base_dir)
    doc["executions"].append(copy.deepcopy(record))
    doc["executions"] = doc["executions"][-MAX_EXECUTIONS_KEPT:]
    _save_doc(user_id, doc, base_dir)
    return record


# -- Execution (the app's own chat road, never a side channel) -----------


async def build_macro_context(session, user_id: str, chat, *,
                              variables: dict | None = None,
                              seed: int | None = None) -> MacroContext:
    """The P-055 context for one chat, from the chat itself:
    the bound character's name, the owner's display name, and
    the history's last messages. Facts the chat does not hold
    stay empty -- nothing is invented for a macro to read."""
    from runmal.characters.service import get_character
    from runmal.chats import service as chats_svc
    from runmal.db.models import User

    char_name = ""
    if getattr(chat, "character_id", None):
        character = await get_character(session, user_id, chat.character_id)
        if character is not None:
            char_name = character.name or ""
    user = await session.get(User, user_id)
    user_name = user.name if user is not None and user.name else "User"
    history = await chats_svc.get_history(session, user_id, chat.id) or []
    last = history[-1].content if history else ""
    last_user = next(
        (m.content for m in reversed(history) if m.role == "user"), "")
    last_char = next(
        (m.content for m in reversed(history) if m.role == "assistant"), "")
    return MacroContext(
        char_name=char_name, user_name=user_name, persona_name="",
        chat_id=chat.id, last_message=last, last_user_message=last_user,
        last_char_message=last_char, variables=dict(variables or {}),
        seed=seed, roll_context=f"quick-reply:{chat.id}")


def _step_provenance(reply: dict, step: dict, index: int) -> dict:
    """The P-075 record for one executed step: origin kind
    ``manual`` (the closed vocabulary has no quick-reply kind)
    with scalar origin facts naming the true road."""
    return prov_mod.build_record(
        origin_kind="manual",
        origin={
            "via": "quick_reply",
            "quick_reply_id": reply["id"],
            "quick_reply_name": reply["name"],
            "step_index": index,
            "sender": step["sender"],
        },
        model=prov_mod.model_section(
            status="unknown" if step["role"] == "assistant"
            else "not_applicable"),
        lore=prov_mod.lore_section(status="not_applicable"),
    )


async def execute_reply(session, user_id: str, chat_id: str, reply_id: str,
                        *, variables: dict | None = None,
                        seed: int | None = None,
                        base_dir: Path | None = None) -> dict | None:
    """Run one reply into one chat, step by step, in order.

    ``None`` when the chat or reply is missing/foreign, or a
    chat-scoped reply is asked into a different chat. A
    disabled reply raises :class:`QuickReplyError` before any
    write. Otherwise an execution record is persisted and
    returned whatever happens: ``ok`` when every step landed,
    ``partial`` when at least one landed and a later step
    failed, ``failed`` when the first step failed.
    """
    from runmal.chats import service as chats_svc

    chat = await chats_svc.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    reply = get_reply(user_id, reply_id, base_dir=base_dir)
    if reply is None:
        return None
    if reply["scope"] == "chat" and reply["chat_id"] != chat_id:
        return None
    if not reply["enabled"]:
        raise QuickReplyError(
            f"quick reply {reply['name']!r} is disabled")
    ctx = await build_macro_context(
        session, user_id, chat, variables=variables, seed=seed)
    record = {
        "id": str(uuid.uuid4()),
        "reply_id": reply["id"],
        "reply_name": reply["name"],
        "chat_id": chat_id,
        "status": "ok",
        "started_at": _now_iso(),
        "steps": [],
        "variables": dict(variables or {}),
    }
    threaded = dict(variables or {})
    failed = False
    for index, step in enumerate(reply["steps"]):
        base = {"index": index, "kind": step["kind"],
                "role": step["role"], "sender": step["sender"]}
        if failed:
            record["steps"].append({**base, "status": "skipped",
                                    "message_id": None, "error": None,
                                    "expanded_text": None})
            continue
        try:
            result = expand_macros(
                step["text"], ctx, strict=True, variables=threaded)
        except MacroError as exc:
            record["steps"].append({**base, "status": "failed",
                                    "message_id": None,
                                    "error": f"MacroError: {exc}",
                                    "expanded_text": None})
            failed = True
            continue
        threaded = dict(result.report.variables)
        expanded = result.text
        if not expanded.strip():
            record["steps"].append({**base, "status": "failed",
                                    "message_id": None,
                                    "error": "expanded text is empty",
                                    "expanded_text": expanded})
            failed = True
            continue
        message = await chats_svc.append_message(
            session, user_id, chat_id, step["role"], expanded,
            provenance=_step_provenance(reply, step, index),
            event_data={"via": "quick_reply",
                        "quick_reply_id": reply["id"],
                        "step_index": index,
                        "sender": step["sender"]})
        record["steps"].append({**base, "status": "ok",
                                "message_id": message.id,
                                "error": None,
                                "expanded_text": expanded})
    applied = sum(1 for s in record["steps"] if s["status"] == "ok")
    if failed:
        record["status"] = "partial" if applied else "failed"
    record["variables"] = threaded
    return _record_execution(user_id, record, base_dir)


# -- The P-081 citizen ------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Quick Replies",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "User-defined one-tap macros: stored "
                       "replies with chained actions and input "
                       "senders, executed through the chat road.",
        "author": "Rúnmál",
        "capabilities": ["chat.events", "ui.slots"],
        "permissions": ["chat.read", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "chat.toolbar",
                "label": "Quick Replies",
                "order": 100,
                "payload": {"kind": "panel", "route": "quick-replies"},
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


class QuickRepliesPlugin:
    """The citizen: a UI contribution plus declared chat
    events whose handler abstains -- chat deletion must never
    silently delete durable user definitions, and executions
    are explicit owner verbs, never event-driven."""

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
                    ) -> tuple[PluginRecord, QuickRepliesPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = QuickRepliesPlugin(base_dir)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS", "MAX_EXECUTIONS_KEPT", "MAX_NAME_CHARS",
    "MAX_REPLIES_PER_USER", "MAX_STEPS", "MAX_TEXT_CHARS",
    "PLUGIN_ID", "PLUGIN_VERSION", "SCOPES", "STEP_KINDS",
    "STEP_ROLES", "STEP_SENDERS", "STORE_SCHEMA", "UI_LOCAL_ID",
    "VERSION", "QuickRepliesPlugin", "QuickReplyError",
    "build_macro_context", "build_manifest", "create_reply",
    "delete_reply", "execute_reply", "get_reply", "list_executions",
    "list_replies", "manifest_data", "register_plugin",
    "reply_from_data", "reply_to_data", "sandbox_grants",
    "step_from_data", "step_to_data", "store_path",
]

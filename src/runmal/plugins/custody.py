"""Plugin data custody (P-094): exportable + deletable, no hostage state.

Roadmap line: "Plugin data custody: a plugin's data is
exportable and deletable with the plugin - no hostage state."

One custody surface over every shipped Part VI citizen
(P094_SCOUT.md is the inventory this module is built from):

- :func:`export_plugin_data` returns ONE document per plugin:
  manifest-stamped, checksummed (the packs canonical-JSON +
  sha256 idiom), with one section per store the citizen holds.
  A section is never silently omitted: it reports exported,
  empty, unavailable (the access road was not supplied - the
  reason is named) or error (a durable store is corrupt - the
  citizen's own refusal text is carried, never a silent empty
  spread over damaged data).
- :func:`delete_plugin_data` deletes the same sections,
  owner-scoped, and reports per-section removed counts. When a
  P-083 manager is supplied and the plugin is pack-managed,
  deletion finishes through ``manager.uninstall`` so the
  ledger row and registration go too - the P-083 hook point,
  now with the data attached. Lifecycle for citizens stays
  with the registry/manager: custody deletes DATA.

Honesty lines (per citizen, from the scout): durable file
stores export VERBATIM (the parsed store document - a section
cannot silently drop a field the store holds); the summarise
citizen's database output (every ChatSummary version + its
kind=summary memories) exports in full; the vector citizen's
data is its INDEX (the founding memories are host data) and
exports doc ids + provenance + the vectors themselves when
the backing store is enumerable, stating plainly when it is
not; in-memory citizens (translate, web search, image
ledger, TTS/STT latest results) export their CURRENT state
or an honest empty - nothing here invents persistence they
do not have; landed P-023 assets and founding chats/messages
are host data, named as references, never custody's to delete.

Wiring: :func:`register_plugin` only (the custody citizen
itself holds no data). ``build_registry`` / ``create_app``
are unchanged. No migration: head stays 0041. Sandbox stance
(P-082): only v1 surface permissions are declared, so the
derived grant set is EMPTY; the custody functions are trusted
host wiring in the register_plugin trust class. The P-093
variables module is imported lazily: on a tree where it has
not landed, its section reports unavailable and its file is
never touched - custody does not delete what it cannot
identify. See docs/PLUGIN_DATA_CUSTODY_2026-11-07.md.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import runmal
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.plugin-custody"
PLUGIN_VERSION = "1.0.0"
VERSION = PLUGIN_VERSION
UI_LOCAL_ID = "plugin-custody-panel"
CUSTODY_FORMAT = "runmal-plugin-custody"
CUSTODY_VERSION = 1

#: Citizen plugin ids this build can custody, in roadmap order.
CITIZEN_PLUGIN_IDS = (
    "runmal.summarise",
    "runmal.vector-storage",
    "runmal.translate",
    "runmal.image-generation",
    "runmal.web-search",
    "runmal.quick-replies",
    "runmal.regex-scripts",
    "runmal.tts",
    "runmal.stt",
    "runmal.expressions",
    "runmal.variables",
    PLUGIN_ID,
)

#: plugin_id -> (module path, store file kind) for the durable
#: per-user file citizens (P-089 idiom and its descendants).
_FILE_STORES = {
    "runmal.quick-replies": "runmal.plugins.quick_replies",
    "runmal.regex-scripts": "runmal.plugins.regex_scripts",
    "runmal.expressions": "runmal.plugins.expressions",
    "runmal.variables": "runmal.plugins.variables",
}

#: plugin_id -> module path for citizens whose manifest can be
#: stamped into an export even when nothing is registered.
_MANIFEST_MODULES = {
    "runmal.summarise": "runmal.plugins.summarise",
    "runmal.vector-storage": "runmal.plugins.vector_storage",
    "runmal.translate": "runmal.plugins.translate",
    "runmal.image-generation": "runmal.plugins.image_generation",
    "runmal.web-search": "runmal.plugins.web_search",
    "runmal.quick-replies": "runmal.plugins.quick_replies",
    "runmal.regex-scripts": "runmal.plugins.regex_scripts",
    "runmal.tts": "runmal.plugins.tts",
    "runmal.stt": "runmal.plugins.stt",
    "runmal.expressions": "runmal.plugins.expressions",
    "runmal.variables": "runmal.plugins.variables",
}


class CustodyError(ValueError):
    """A custody refusal (house 422): unknown plugin, bad owner."""


class UnknownPluginError(CustodyError):
    """No adapter, no ledger row, no registration: unknown id (404)."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _checksum(payload) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def verify_custody_checksum(document: dict) -> bool:
    """Recompute the document checksum over its stamped core."""
    if not isinstance(document, dict):
        return False
    core = {"plugin_id": document.get("plugin_id"),
            "owner_id": document.get("owner_id"),
            "sections": document.get("sections")}
    return document.get("content_sha256") == _checksum(core)


def custody_coverage() -> dict:
    """The adapter table as data: what this build can custody."""
    return {
        "format": CUSTODY_FORMAT,
        "custody_version": CUSTODY_VERSION,
        "plugin_id": PLUGIN_ID,
        "citizens": list(CITIZEN_PLUGIN_IDS),
        "durable_file": sorted(_FILE_STORES),
        "database": ["runmal.summarise"],
        "instance_memory": [
            "runmal.vector-storage", "runmal.translate",
            "runmal.image-generation", "runmal.web-search",
            "runmal.tts", "runmal.stt"],
        "stateless": [PLUGIN_ID],
        "universal_sections": ["host_ledger", "registration"],
    }


def _check_user_id(user_id) -> str:
    if not isinstance(user_id, str) or not user_id:
        raise CustodyError(f"invalid user_id: {user_id!r}")
    try:
        uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        raise CustodyError(f"invalid user_id: {user_id!r}") from None
    return user_id


def _import_module(path: str):
    import importlib
    return importlib.import_module(path)


# -- durable file citizens -------------------------------------------------


def _doc_counts(doc: dict) -> dict:
    counts: dict = {}
    for key, value in doc.items():
        if key == "schema":
            continue
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value)
    return counts


def _file_section(plugin_id: str, *, user_id, base_dir, delete: bool) -> dict:
    module_path = _FILE_STORES[plugin_id]
    name = module_path.rsplit(".", 1)[-1] + "_store"
    base = {"name": name, "kind": "durable_file"}
    if user_id is None:
        return {**base, "status": "unavailable" if not delete else "unavailable",
                "reason": "owner user_id not supplied: file stores are per-owner"}
    try:
        module = _import_module(module_path)
    except ImportError:
        return {**base, "status": "unavailable",
                "reason": f"module {module_path} is not present in this build; "
                          "custody never touches a store it cannot identify"}
    _check_user_id(user_id)
    path = Path(module.store_path(user_id, base_dir))
    if delete:
        if not path.exists():
            return {**base, "status": "empty", "store_path": str(path),
                    "removed": {"files": 0}}
        counts = {}
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                counts = _doc_counts(doc)
        except (OSError, ValueError):
            counts = {}
        path.unlink()
        return {**base, "status": "deleted", "store_path": str(path),
                "removed": {"files": 1, **counts}}
    if not path.exists():
        return {**base, "status": "empty", "store_path": str(path),
                "schema": getattr(module, "STORE_SCHEMA", None),
                "document": None, "counts": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {**base, "status": "error", "store_path": str(path),
                "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(doc, dict):
        return {**base, "status": "error", "store_path": str(path),
                "error": "store document is not a JSON object"}
    schema = getattr(module, "STORE_SCHEMA", None)
    if schema is not None and doc.get("schema") != schema:
        return {**base, "status": "error", "store_path": str(path),
                "error": f"store schema mismatch: {doc.get(chr(115)+'chema')!r} "
                         f"!= {schema!r}"}
    return {**base, "status": "exported", "store_path": str(path),
            "schema": doc.get("schema"), "document": doc,
            "counts": _doc_counts(doc)}


# -- owner scope helpers -----------------------------------------------------


async def _owner_chat_ids(session, user_id) -> set:
    from sqlalchemy import select

    from runmal.db.models import Chat

    rows = await session.scalars(
        select(Chat.id).where(Chat.user_id == user_id))
    return {str(row) for row in rows}


async def _owner_character_ids(session, user_id) -> set:
    from sqlalchemy import select

    from runmal.db.models import Character

    rows = await session.scalars(
        select(Character.id).where(Character.user_id == user_id))
    return {str(row) for row in rows}


def _keep(chat_id, allowed) -> bool:
    return allowed is None or str(chat_id) in allowed


# -- summarise database citizen ----------------------------------------------


def _summary_row_to_dict(row) -> dict:
    return {
        "id": row.id, "user_id": row.user_id, "chat_id": row.chat_id,
        "version": row.version, "summary": row.summary,
        "source_first_id": row.source_first_id,
        "source_last_id": row.source_last_id,
        "source_count": row.source_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _summarise_section(*, user_id, session, delete: bool) -> dict:
    base = {"name": "summarise_store", "kind": "database"}
    if session is None or user_id is None:
        missing = []
        if session is None:
            missing.append("session")
        if user_id is None:
            missing.append("owner user_id")
        return {**base, "status": "unavailable",
                "reason": "database road not supplied: "
                          + " and ".join(missing) + " required"}
    _check_user_id(user_id)
    from sqlalchemy import delete as sa_delete, select

    from runmal.db.models import ChatSummary
    from runmal.memory import service as memory_service
    from runmal.memory.models import memory_to_dict, source_to_dict

    rows = list(await session.scalars(
        select(ChatSummary).where(ChatSummary.user_id == user_id)
        .order_by(ChatSummary.chat_id, ChatSummary.version)))
    summary_ids = {row.id for row in rows}
    memories = []
    for memory in await memory_service.list_memories(
            session, user_id, kind="summary"):
        data = memory_to_dict(memory)
        extractor = data.get("extractor") or {}
        if extractor.get("summary_id") in summary_ids:
            sources = await memory_service.list_sources(session, memory.id)
            data["sources"] = [source_to_dict(s) for s in sources]
            memories.append((memory, data))
    if delete:
        removed_memories = 0
        for memory, _data in memories:
            if await memory_service.delete_memory(session, user_id, memory.id):
                removed_memories += 1
        removed_summaries = 0
        if summary_ids:
            result = await session.execute(
                sa_delete(ChatSummary).where(ChatSummary.id.in_(summary_ids)))
            removed_summaries = result.rowcount or 0
            await session.flush()
        return {**base, "status": "deleted" if (rows or memories) else "empty",
                "removed": {"summaries": removed_summaries,
                            "memories": removed_memories}}
    payload = {
        "summaries": [_summary_row_to_dict(row) for row in rows],
        "memories": [data for _memory, data in memories],
    }
    return {**base, "status": "exported" if (rows or memories) else "empty",
            "summaries": payload["summaries"],
            "memories": payload["memories"],
            "counts": {"summaries": len(rows), "memories": len(memories)}}


# -- vector-storage index citizen --------------------------------------------


def _vector_section(instance, *, delete: bool, allowed_chats=None,
                    allowed_characters=None) -> dict:
    base = {"name": "vector_index", "kind": "instance_memory"}
    index = getattr(instance, "index", None)
    if index is None:
        return {**base, "status": "unavailable",
                "reason": "vector index is unbound on this instance"}
    meta = getattr(index, "_meta", {}) or {}
    scoped = {}
    for doc_id in index.doc_ids():
        entry = meta.get(doc_id)
        if entry is None:
            continue
        kind, scope_id, _memory_id = entry
        if kind == "chat" and not _keep(scope_id, allowed_chats):
            continue
        if kind == "character" and not _keep(scope_id, allowed_characters):
            continue
        scoped[doc_id] = entry
    scopes = {}
    for doc_id, (kind, scope_id, memory_id) in scoped.items():
        key = kind + "|" + str(scope_id)
        bucket = scopes.setdefault(key, {"scope_kind": kind,
                                         "scope_id": scope_id,
                                         "doc_ids": [], "memory_ids": []})
        bucket["doc_ids"].append(doc_id)
        bucket["memory_ids"].append(memory_id)
    prov = getattr(index, "last_provenance", None)
    prov_data = prov.to_dict() if prov is not None else None
    if delete:
        removed = 0
        for bucket in scopes.values():
            index.clear_scope(bucket["scope_kind"], bucket["scope_id"])
            removed += len(bucket["doc_ids"])
        return {**base, "status": "deleted" if removed else "empty",
                "removed": {"vectors": removed, "scopes": len(scopes)}}
    from runmal.memory.vectorstore import InMemoryVectorStore, space_key

    store = getattr(index, "store", None)
    vectors = None
    vectors_note = None
    if isinstance(store, InMemoryVectorStore) and prov is not None:
        bucket = store._spaces.get(space_key(prov), {})
        vectors = {doc_id: list(bucket[doc_id]) for doc_id in scoped
                   if doc_id in bucket}
    else:
        vectors_note = ("vectors_not_enumerable: the founding vector-store "
                        "contract exposes no enumeration of stored vectors; "
                        "the index manifest above is complete and the vectors "
                        "are rebuildable from the founding memories, which "
                        "are host data, not plugin data")
    status = "exported" if scoped else "empty"
    return {**base, "status": status, "provenance": prov_data,
            "scopes": [scopes[key] for key in sorted(scopes)],
            "vectors": vectors, "vectors_note": vectors_note,
            "counts": {"vectors": len(scoped), "scopes": len(scopes)}}


# -- in-memory citizens --------------------------------------------------------


def _translate_section(instance, *, delete: bool, allowed=None) -> dict:
    base = {"name": "translate_state", "kind": "instance_memory"}
    chats = sorted({str(c) for c in instance._chat_configs}
                   | {str(k[0]) for k in instance._translations})
    chats = [c for c in chats if _keep(c, allowed)]
    if delete:
        removed_rows = 0
        removed_configs = 0
        for chat_id in chats:
            removed_rows += len(instance.translations_for(chat_id))
            if chat_id in instance._chat_configs:
                removed_configs += 1
            instance.clear_chat_config(chat_id)
        return {**base, "status": "deleted" if chats else "empty",
                "removed": {"translations": removed_rows,
                            "configs": removed_configs}}
    per_chat = [{"chat_id": c, "status": instance.translation_status(c),
                 "translations": instance.translations_for(c)}
                for c in chats]
    total = sum(len(row["translations"]) for row in per_chat)
    return {**base, "status": "exported" if chats else "empty",
            "chats": per_chat,
            "counts": {"chats": len(chats), "translations": total}}


def _web_search_section(instance, *, delete: bool, allowed=None) -> dict:
    base = {"name": "web_search_state", "kind": "instance_memory"}
    chats = sorted({str(c) for c in instance._chat_configs}
                   | {str(c) for c in instance._results})
    chats = [c for c in chats if _keep(c, allowed)]
    if delete:
        removed_results = 0
        removed_configs = 0
        for chat_id in chats:
            if chat_id in instance._results:
                removed_results += 1
            if chat_id in instance._chat_configs:
                removed_configs += 1
            instance.clear_chat_config(chat_id)
        return {**base, "status": "deleted" if chats else "empty",
                "removed": {"result_sets": removed_results,
                            "configs": removed_configs}}
    per_chat = [{"chat_id": c, "status": instance.search_status(c)}
                for c in chats]
    return {**base, "status": "exported" if chats else "empty",
            "chats": per_chat, "counts": {"chats": len(chats)}}


def _image_section(instance, *, delete: bool, allowed=None) -> dict:
    base = {"name": "image_generation_state", "kind": "instance_memory"}
    enabled = [c for c in instance.enabled_chat_ids() if _keep(c, allowed)]
    ledger = [dict(r) for r in instance.history()
              if _keep(r.get("chat_id"), allowed)]
    if delete:
        removed_ledger = 0
        if allowed is None:
            removed_ledger = len(instance._ledger)
            instance._ledger[:] = []
            removed_enabled = len(instance._enabled_chats)
            instance._enabled_chats.clear()
        else:
            kept = [r for r in instance._ledger
                    if str(r.get("chat_id")) not in allowed]
            removed_ledger = len(instance._ledger) - len(kept)
            instance._ledger[:] = kept
            removed_enabled = 0
            for chat_id in enabled:
                instance.set_chat_enabled(chat_id, False)
                removed_enabled += 1
        return {**base,
                "status": "deleted" if (removed_ledger or removed_enabled) else "empty",
                "removed": {"ledger_records": removed_ledger,
                            "enabled_chats": removed_enabled}}
    landed = sorted({r["asset_id"] for r in ledger if r.get("asset_id")})
    return {**base, "status": "exported" if (enabled or ledger) else "empty",
            "enabled_chat_ids": enabled, "ledger": ledger,
            "landed_asset_ids": landed,
            "landed_assets_note": ("landed image bytes are P-023 character "
                                    "assets - host data in the character "
                                    "library, named here as references only; "
                                    "custody deletion never deletes them"),
            "counts": {"enabled_chats": len(enabled),
                       "ledger_records": len(ledger)}}


def _tts_section(instance, *, delete: bool, allowed=None) -> dict:
    base = {"name": "tts_state", "kind": "instance_memory"}
    chats = sorted({str(c) for c in instance._last_by_chat}
                   | {str(c) for c in instance._observed})
    chats = [c for c in chats if _keep(c, allowed)]
    if delete:
        removed_results = sum(1 for c in chats if c in instance._last_by_chat)
        removed_observed = sum(1 for c in chats if c in instance._observed)
        for chat_id in chats:
            instance.clear_chat(chat_id)
        return {**base, "status": "deleted" if chats else "empty",
                "removed": {"results": removed_results,
                            "observed": removed_observed}}
    per_chat = [instance.speech_status(c) for c in chats]
    return {**base, "status": "exported" if chats else "empty",
            "chats": per_chat, "counts": {"chats": len(chats)}}


def _stt_section(instance, *, delete: bool, allowed=None) -> dict:
    base = {"name": "stt_state", "kind": "instance_memory"}
    chats = sorted(str(c) for c in instance._last_by_chat)
    chats = [c for c in chats if _keep(c, allowed)]
    if delete:
        removed = len(chats)
        for chat_id in chats:
            instance.clear_chat(chat_id)
        return {**base, "status": "deleted" if chats else "empty",
                "removed": {"transcripts": removed}}
    per_chat = [instance.transcription_status(c) for c in chats]
    return {**base, "status": "exported" if chats else "empty",
            "chats": per_chat, "counts": {"chats": len(chats)}}


_INSTANCE_NAMES = {
    "runmal.vector-storage": "vector_index",
    "runmal.translate": "translate_state",
    "runmal.image-generation": "image_generation_state",
    "runmal.web-search": "web_search_state",
    "runmal.tts": "tts_state",
    "runmal.stt": "stt_state",
}


async def _instance_section(plugin_id, *, instances, session, user_id,
                            delete: bool) -> dict:
    name = _INSTANCE_NAMES[plugin_id]
    kind = "instance_memory"
    instance = (instances or {}).get(plugin_id)
    if instance is None:
        return {"name": name, "kind": kind, "status": "unavailable",
                "reason": "live instance not supplied: in-memory state is "
                          "reachable only through the instance"}
    allowed = None
    if session is not None and user_id is not None:
        allowed = await _owner_chat_ids(session, user_id)
    if plugin_id == "runmal.vector-storage":
        allowed_characters = None
        if session is not None and user_id is not None:
            allowed_characters = await _owner_character_ids(session, user_id)
        return _vector_section(instance, delete=delete, allowed_chats=allowed,
                               allowed_characters=allowed_characters)
    handler = {
        "runmal.translate": _translate_section,
        "runmal.web-search": _web_search_section,
        "runmal.image-generation": _image_section,
        "runmal.tts": _tts_section,
        "runmal.stt": _stt_section,
    }[plugin_id]
    return handler(instance, delete=delete, allowed=allowed)


# -- universal sections: host ledger + registration ---------------------------


def _ledger_section(plugin_id, *, manager) -> dict:
    base = {"name": "host_ledger", "kind": "host_ledger"}
    if manager is None:
        return {**base, "status": "unavailable",
                "reason": "plugin manager not supplied: the P-083 ledger "
                          "is reachable only through the manager"}
    row = manager.row_for(plugin_id)
    if row is None:
        return {**base, "status": "empty", "row": None}
    return {**base, "status": "exported", "row": row}


def _registration_section(plugin_id, *, registry) -> dict:
    base = {"name": "registration", "kind": "registration"}
    if registry is None:
        return {**base, "status": "unavailable",
                "reason": "plugin registry not supplied"}
    record = registry.find(plugin_id)
    if record is None:
        return {**base, "status": "empty", "record": None}
    from runmal.plugins.service import record_detail_to_dict

    return {**base, "status": "exported",
            "record": record_detail_to_dict(record, registry)}


def _manifest_for(plugin_id, registry):
    if registry is not None:
        record = registry.find(plugin_id)
        if record is not None:
            return manifest_to_data(record.manifest)
    if plugin_id == PLUGIN_ID:
        return manifest_data()
    path = _MANIFEST_MODULES.get(plugin_id)
    if path is None:
        return None
    try:
        return _import_module(path).manifest_data()
    except Exception:
        return None


def _is_known(plugin_id, *, registry, manager) -> bool:
    if plugin_id in CITIZEN_PLUGIN_IDS:
        return True
    if registry is not None and registry.find(plugin_id) is not None:
        return True
    if manager is not None and manager.row_for(plugin_id) is not None:
        return True
    return False


async def _data_sections(plugin_id, *, user_id, base_dir, session,
                         instances, delete: bool) -> list:
    if plugin_id in _FILE_STORES:
        return [_file_section(plugin_id, user_id=user_id,
                              base_dir=base_dir, delete=delete)]
    if plugin_id == "runmal.summarise":
        return [await _summarise_section(user_id=user_id, session=session,
                                         delete=delete)]
    if plugin_id in _INSTANCE_NAMES:
        return [await _instance_section(plugin_id, instances=instances,
                                        session=session, user_id=user_id,
                                        delete=delete)]
    return []


# -- the two verbs -------------------------------------------------------------


async def export_plugin_data(plugin_id, *, user_id=None, base_dir=None,
                             session=None, instances=None, registry=None,
                             manager=None) -> dict:
    """Export ONE plugin's data as one checksummed document.

    Every store the citizen holds appears as a section; a
    section the caller gave no access road for reports
    ``unavailable`` with its reason, a corrupt durable store
    reports ``error`` with the refusal text, and nothing is
    ever silently omitted. An id with no adapter, no ledger
    row and no registration raises :class:`UnknownPluginError`.
    """
    if not isinstance(plugin_id, str) or not plugin_id:
        raise CustodyError(f"invalid plugin_id: {plugin_id!r}")
    if not _is_known(plugin_id, registry=registry, manager=manager):
        raise UnknownPluginError(f"unknown plugin: {plugin_id!r}")
    sections = await _data_sections(
        plugin_id, user_id=user_id, base_dir=base_dir, session=session,
        instances=instances, delete=False)
    sections.append(_ledger_section(plugin_id, manager=manager))
    sections.append(_registration_section(plugin_id, registry=registry))
    core = {"plugin_id": plugin_id, "owner_id": user_id, "sections": sections}
    return {
        "format": CUSTODY_FORMAT, "custody_version": CUSTODY_VERSION,
        "kind": "plugin_data_export", "plugin_id": plugin_id,
        "exported_at": _now_iso(),
        "app_version": getattr(runmal, "__version__", None),
        "owner_id": user_id,
        "manifest": _manifest_for(plugin_id, registry),
        "coverage": list(CITIZEN_PLUGIN_IDS),
        "sections": sections, "content_sha256": _checksum(core),
    }


async def delete_plugin_data(plugin_id, *, user_id=None, base_dir=None,
                             session=None, instances=None, registry=None,
                             manager=None) -> dict:
    """Delete ONE plugin's data, owner-scoped, and report it.

    Deletes the same sections :func:`export_plugin_data`
    exports. Database deletion is flush-only (the caller
    commits, the S404 pattern). When a manager is supplied
    and the plugin is pack-managed, deletion finishes through
    ``manager.uninstall`` so the ledger row and registration
    go too; lifecycle for citizens stays with the registry /
    manager - custody deletes DATA. Idempotent: deleting what
    is already gone reports zero counts, never an error.
    Instance state is filtered to the owner's chats only when
    BOTH a session and a user_id are supplied; with no session
    the caller is trusted in-process host code operating on
    its own instances.
    """
    if not isinstance(plugin_id, str) or not plugin_id:
        raise CustodyError(f"invalid plugin_id: {plugin_id!r}")
    if not _is_known(plugin_id, registry=registry, manager=manager):
        raise UnknownPluginError(f"unknown plugin: {plugin_id!r}")
    sections = await _data_sections(
        plugin_id, user_id=user_id, base_dir=base_dir, session=session,
        instances=instances, delete=True)
    ledger_base = {"name": "host_ledger", "kind": "host_ledger"}
    if manager is None:
        sections.append({**ledger_base, "status": "unavailable",
                         "reason": "plugin manager not supplied: the P-083 "
                                   "ledger is reachable only through the "
                                   "manager", "removed": {}})
    elif manager.row_for(plugin_id) is None:
        sections.append({**ledger_base, "status": "empty",
                         "removed": {"ledger_rows": 0}})
    else:
        try:
            manager.uninstall(plugin_id)
            sections.append({**ledger_base, "status": "deleted",
                             "removed": {"ledger_rows": 1,
                                         "unregistered": True}})
        except Exception as exc:
            sections.append({**ledger_base, "status": "error",
                             "error": f"{type(exc).__name__}: {exc}",
                             "removed": {}})
    sections.append({"name": "registration", "kind": "registration",
                     "status": "not_applicable",
                     "note": "custody deletes data, not lifecycle: a "
                             "citizen registration is removed by the "
                             "registry/manager, or above via uninstall "
                             "for pack-managed plugins"})
    core = {"plugin_id": plugin_id, "owner_id": user_id, "sections": sections}
    return {
        "format": CUSTODY_FORMAT, "custody_version": CUSTODY_VERSION,
        "kind": "plugin_data_deletion", "plugin_id": plugin_id,
        "deleted_at": _now_iso(), "owner_id": user_id,
        "sections": sections, "content_sha256": _checksum(core),
    }


# -- The P-081 citizen ---------------------------------------------------------


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Plugin Data Custody",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Plugin data custody: every plugin's data "
                       "is exportable and deletable with the plugin "
                       "- no hostage state.",
        "author": "Rúnmál",
        "capabilities": ["ui.slots"],
        "permissions": ["ui.contribute"],
        "events": [],
        "prompt_hooks": [],
        "ui_slots": [
            {
                "id": UI_LOCAL_ID,
                "slot": "settings.panel",
                "label": "Plugin Data Custody",
                "order": 120,
                "payload": {"kind": "panel", "route": "plugin-custody"},
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


class CustodyPlugin:
    """The citizen: a settings-panel contribution only.

    The custody verbs are module functions (trusted host
    wiring, the register_plugin trust class); the citizen
    itself holds NO data - its own custody export is the
    honest empty over its universal sections, pinned by the
    battery.
    """

    @property
    def manifest(self):
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(on_event=self.on_event)

    async def on_event(self, event) -> None:
        return None


def register_plugin(registry: PluginRegistry, *,
                    enable: bool = False,
                    ) -> tuple[PluginRecord, CustodyPlugin]:
    """Register the citizen into ``registry`` (trusted code only)."""
    plugin = CustodyPlugin()
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "CITIZEN_PLUGIN_IDS", "CUSTODY_FORMAT", "CUSTODY_VERSION",
    "PLUGIN_ID", "PLUGIN_VERSION", "UI_LOCAL_ID", "VERSION",
    "CustodyError", "CustodyPlugin", "UnknownPluginError",
    "build_manifest", "custody_coverage", "delete_plugin_data",
    "export_plugin_data", "manifest_data", "register_plugin",
    "sandbox_grants", "verify_custody_checksum",
]

"""Chat data bank (P-074): per-chat attached documents the model
can read, scoped and budgeted.

A data bank holds text documents attached to ONE chat (chat
scope) plus documents attached to the owner (global scope, read
by every chat of that owner -- census ST-60's shape). Attached
documents join the prompt as typed slots, but ONLY within a
declared per-chat token budget: selection includes whole
documents or excludes them whole with a recorded reason -- a
document is never silently truncated to fit.

Storage rides the P-067 checkpoint pattern, proven at base: a
document is a self-contained JSON file on disk -- no DB rows, no
migration (head stays 0038) -- sealed by a SHA-256 checksum over
the canonical bytes of the document payload, written atomically
(tmp sibling, chmod 0o600, replace). Files live at
``data_dir()/databank/<user_id>/<scope_key>/<doc_id>.json`` where
``scope_key`` is the chat id or ``_global``. The per-chat budget
lives in a likewise-sealed ``_settings.json`` in the chat's
scope directory. Listing is a directory scan; there is no index
file to disagree with the directory.

Budget honesty:

- One counter: every count comes from :mod:`runmal.tokens`
  (``estimate_tokens`` by default, or the caller's counter
  labelled EXACT) over the RENDERED document text -- the exact
  text the prompt slot carries -- so accounting equals slot
  spend for the same document.
- The governor (P-058) counts slot kind ``databank`` under its
  ``context`` section by its documented fallback, so the spend
  is visible in the whole-prompt budget; the composer still
  enforces the total input budget on top of the bank budget.
- Accounting carries ids, names, scopes, counts and reasons
  only -- never content (S214).

Every chat-scope operation verifies the owned chat FIRST
(``service._get_owned_chat``) before any file is touched, and a
document id is validated before any path is built from it: a
missing or foreign chat, and an unknown document, read as
None/False; a malformed id or field raises ValueError; a
corrupt, tampered, or foreign payload raises DataBankError.
Unknown and corrupt stay distinct, always.

Clean-room: built from Runmal's own checkpoint / governor /
composer contracts only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.auth import data_dir
from runmal.chats.service import _get_owned_chat, _record_event
from runmal.prompt.slots import Slot, baseline_order
from runmal.tokens import TokenQuality, estimate_tokens

FORMAT_NAME = "runmal-databank"
FORMAT_VERSION = 1
SETTINGS_FORMAT_NAME = "runmal-databank-settings"

EVENT_DATABANK_ATTACHED = "databank.attached"
EVENT_DATABANK_UPDATED = "databank.updated"
EVENT_DATABANK_DETACHED = "databank.detached"
EVENT_DATABANK_BUDGET_CHANGED = "databank.budget_changed"

SCOPE_CHAT = "chat"
SCOPE_GLOBAL = "global"
GLOBAL_SCOPE_KEY = "_global"
SETTINGS_FILENAME = "_settings.json"

DEFAULT_BUDGET_TOKENS = 2000
MAX_BUDGET_TOKENS = 100_000
MAX_CONTENT_CHARS = 200_000
MAX_NAME_CHARS = 200
MAX_DOCS_PER_SCOPE = 100
MIN_PRIORITY = -100
MAX_PRIORITY = 100

ALLOWED_CONTENT_TYPES = frozenset({
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
    "application/json",
})

REASON_DISABLED = "disabled"
REASON_OVER_BUDGET = "over_databank_budget"

#: The governor section databank slots are counted under (the
#: P-058 fallback for kinds it does not name is "context").
GOVERNOR_SECTION = "context"


class DataBankError(Exception):
    """A data-bank payload is corrupt, tampered, foreign, or of
    an unsupported format or version (mirrors ``CheckpointError``:
    a plain Exception, NOT a ValueError subclass, so the two map
    distinctly even though both land on 422 at the router)."""


_DOC_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _validate_doc_id(doc_id) -> None:
    """Raise ValueError unless ``doc_id`` is a plain filename
    stem. Called before ANY path is constructed from the id."""
    if (
        not isinstance(doc_id, str)
        or doc_id in (".", "..")
        or "/" in doc_id
        or "\\" in doc_id
        or "\x00" in doc_id
        or doc_id.startswith("_")
        or not _DOC_ID_RE.fullmatch(doc_id)
    ):
        raise ValueError(f"malformed document id: {doc_id!r}")


def _root(base_dir: Path | None) -> Path:
    return base_dir if base_dir is not None else data_dir()


def _scope_key(scope: str, chat_id: str | None) -> str:
    return chat_id if scope == SCOPE_CHAT else GLOBAL_SCOPE_KEY


def _scope_dir(user_id: str, scope: str, chat_id: str | None, base_dir: Path | None = None) -> Path:
    return _root(base_dir) / "databank" / user_id / _scope_key(scope, chat_id)


def _doc_path(user_id: str, scope: str, chat_id: str | None, doc_id: str, base_dir: Path | None = None) -> Path:
    """The document's file path. Only ever called after id
    validation; defence in depth after the join: the resolved
    file's parent must be the resolved scope directory."""
    directory = _scope_dir(user_id, scope, chat_id, base_dir)
    path = directory / f"{doc_id}.json"
    if path.resolve().parent != directory.resolve():
        raise ValueError(f"document path escapes its directory: {doc_id!r}")
    return path


def _settings_path(user_id: str, scope: str, chat_id: str | None, base_dir: Path | None = None) -> Path:
    return _scope_dir(user_id, scope, chat_id, base_dir) / SETTINGS_FILENAME


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _checksum(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# ----------------------------------------------------------------
# Validation (strict boundary: malformed is refused, never repaired)
# ----------------------------------------------------------------


def _validate_name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("document name must be a non-empty string")
    if len(value) > MAX_NAME_CHARS:
        raise ValueError(f"document name must be <= {MAX_NAME_CHARS} characters")
    return value


def _validate_content(value) -> str:
    if not isinstance(value, str):
        raise ValueError("document content must be a string")
    if len(value) > MAX_CONTENT_CHARS:
        raise ValueError(f"document content must be <= {MAX_CONTENT_CHARS} characters")
    return value


def _validate_content_type(value) -> str:
    if value is None:
        return "text/plain"
    if not isinstance(value, str) or value not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"unsupported content_type: {value!r}")
    return value


def _validate_enabled(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, bool):
        raise ValueError("enabled must be a bool")
    return value


def _validate_priority(value) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("priority must be an int")
    if value < MIN_PRIORITY or value > MAX_PRIORITY:
        raise ValueError(f"priority must be in {MIN_PRIORITY}..{MAX_PRIORITY}")
    return value


def _validate_budget(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("budget_tokens must be an int")
    if value < 0 or value > MAX_BUDGET_TOKENS:
        raise ValueError(f"budget_tokens must be in 0..{MAX_BUDGET_TOKENS}")
    return value


# ----------------------------------------------------------------
# File IO (sync; the async API below owns chat verification)
# ----------------------------------------------------------------


def _write_document(user_id, doc: dict, base_dir=None) -> None:
    envelope = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "document": doc,
        "checksum": _checksum(doc),
    }
    _atomic_write(_doc_path(user_id, doc["scope"], doc.get("chat_id"), doc["id"], base_dir), envelope)


def _read_document_at(path: Path, user_id: str, scope: str, chat_id: str | None) -> dict:
    """Read + verify one document file. Raises DataBankError on
    any corruption, tampering, or foreign payload."""
    try:
        raw = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataBankError(f"unreadable data-bank document: {path.name}") from exc
    if not isinstance(raw, dict) or raw.get("format") != FORMAT_NAME:
        raise DataBankError(f"foreign data-bank payload: {path.name}")
    if raw.get("version") != FORMAT_VERSION:
        raise DataBankError(f"unsupported data-bank version: {path.name}")
    doc = raw.get("document")
    if not isinstance(doc, dict) or raw.get("checksum") != _checksum(doc):
        raise DataBankError(f"data-bank checksum mismatch: {path.name}")
    if doc.get("scope") != scope or doc.get("chat_id") != chat_id:
        raise DataBankError(f"data-bank document filed under the wrong scope: {path.name}")
    if path.stem != doc.get("id"):
        raise DataBankError(f"data-bank document id does not match its file: {path.name}")
    return doc


def _list_scope_docs(user_id: str, scope: str, chat_id: str | None, base_dir=None) -> list[dict]:
    directory = _scope_dir(user_id, scope, chat_id, base_dir)
    if not directory.is_dir():
        return []
    docs = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("_"):
            continue  # the settings file is not a document
        docs.append(_read_document_at(path, user_id, scope, chat_id))
    docs.sort(key=lambda d: (d.get("created_at") or "", d.get("id") or ""))
    return docs


def _read_budget(user_id: str, scope: str, chat_id: str | None, base_dir=None) -> int:
    path = _settings_path(user_id, scope, chat_id, base_dir)
    if not path.exists():
        return DEFAULT_BUDGET_TOKENS
    try:
        raw = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataBankError("unreadable data-bank settings") from exc
    if not isinstance(raw, dict) or raw.get("format") != SETTINGS_FORMAT_NAME or raw.get("version") != FORMAT_VERSION:
        raise DataBankError("foreign data-bank settings payload")
    payload = {"budget_tokens": raw.get("budget_tokens")}
    if raw.get("checksum") != _checksum(payload):
        raise DataBankError("data-bank settings checksum mismatch")
    return _validate_budget(raw.get("budget_tokens"))


def _write_budget(user_id: str, scope: str, chat_id: str | None, budget: int, base_dir=None) -> None:
    envelope = {
        "format": SETTINGS_FORMAT_NAME,
        "version": FORMAT_VERSION,
        "budget_tokens": budget,
        "checksum": _checksum({"budget_tokens": budget}),
    }
    _atomic_write(_settings_path(user_id, scope, chat_id, base_dir), envelope)


# ----------------------------------------------------------------
# Rendering, counting, selection, accounting (pure)
# ----------------------------------------------------------------


def render_document(doc: dict) -> str:
    """The exact model-facing text for a document -- the text its
    prompt slot carries, and the text its tokens are counted on."""
    return f"[Data bank: {doc['name']}]\n{doc['content']}"


def document_tokens(doc: dict, counter=None) -> int:
    return (counter or estimate_tokens)(render_document(doc))


def document_to_dict(doc: dict, *, include_content: bool = False, counter=None) -> dict:
    out = {
        "id": doc["id"],
        "scope": doc["scope"],
        "chat_id": doc.get("chat_id"),
        "name": doc["name"],
        "content_type": doc["content_type"],
        "enabled": doc["enabled"],
        "priority": doc["priority"],
        "chars": len(doc["content"]),
        "tokens": document_tokens(doc, counter),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }
    if include_content:
        out["content"] = doc["content"]
    return out


@dataclass(frozen=True)
class Selection:
    included: tuple
    excluded: tuple  # (doc, reason, tokens)
    budget_tokens: int
    spent_tokens: int
    count_quality: TokenQuality

    @property
    def remaining_tokens(self) -> int:
        return self.budget_tokens - self.spent_tokens


def _selection_key(doc: dict) -> tuple:
    return (
        -(doc.get("priority") or 0),
        0 if doc.get("scope") == SCOPE_CHAT else 1,
        doc.get("created_at") or "",
        doc.get("id") or "",
    )


def select_documents(docs, budget_tokens: int, counter=None) -> Selection:
    """Greedy whole-document selection within ``budget_tokens``.

    Enabled documents are considered in selection order (higher
    priority first, chat scope before global, then attach order);
    a document joins only if its WHOLE rendered cost fits the
    remaining budget. Nothing is truncated, ever.
    """
    budget = _validate_budget(budget_tokens)
    count = counter or estimate_tokens
    included: list = []
    excluded: list = []
    spent = 0
    for doc in sorted(docs, key=_selection_key):
        tokens = document_tokens(doc, count)
        if not doc.get("enabled", True):
            excluded.append((doc, REASON_DISABLED, tokens))
        elif spent + tokens <= budget:
            included.append(doc)
            spent += tokens
        else:
            excluded.append((doc, REASON_OVER_BUDGET, tokens))
    return Selection(
        included=tuple(included),
        excluded=tuple(excluded),
        budget_tokens=budget,
        spent_tokens=spent,
        count_quality=TokenQuality.EXACT if counter is not None else TokenQuality.ESTIMATED,
    )


def accounting_to_dict(selection: Selection) -> dict:
    """Spend accounting: ids, names, scopes, counts, reasons --
    never content (S214)."""
    quality = selection.count_quality
    return {
        "budget_tokens": selection.budget_tokens,
        "spent_tokens": selection.spent_tokens,
        "remaining_tokens": selection.remaining_tokens,
        "count_quality": quality.value if isinstance(quality, TokenQuality) else quality,
        "governor_section": GOVERNOR_SECTION,
        "included": [
            {
                "id": doc["id"],
                "name": doc["name"],
                "scope": doc["scope"],
                "tokens": document_tokens(doc),
            }
            for doc in selection.included
        ],
        "excluded": [
            {
                "id": doc["id"],
                "name": doc["name"],
                "scope": doc["scope"],
                "tokens": tokens,
                "reason": reason,
            }
            for doc, reason, tokens in selection.excluded
        ],
    }


def slots_for_selection(selection: Selection) -> list[Slot]:
    """One prompt slot per included document, in selection order."""
    return [
        Slot(
            id=f"databank/{doc['id']}",
            kind="databank",
            role="system",
            content=render_document(doc),
            order=baseline_order("lore_before"),
            priority=doc.get("priority") or 0,
            provenance=f"databank:{doc['scope']}:{doc['name']}",
        )
        for doc in selection.included
    ]


# ----------------------------------------------------------------
# Async API (chat scope verifies the owned chat FIRST)
# ----------------------------------------------------------------


async def _verify_scope(session: AsyncSession, user_id: str, scope: str, chat_id: str | None) -> bool:
    if scope == SCOPE_GLOBAL:
        return True
    if not chat_id:
        raise ValueError("chat scope requires a chat_id")
    return await _get_owned_chat(session, user_id, chat_id) is not None


def _scope_docs_with_globals(user_id: str, scope: str, chat_id: str | None, base_dir=None) -> list[dict]:
    docs = _list_scope_docs(user_id, scope, chat_id, base_dir)
    if scope == SCOPE_CHAT:
        docs = docs + _list_scope_docs(user_id, SCOPE_GLOBAL, None, base_dir)
    return docs


async def attach_document(
    session: AsyncSession,
    user_id: str,
    scope: str,
    chat_id: str | None = None,
    *,
    name=None,
    content=None,
    content_type=None,
    enabled=None,
    priority=None,
    base_dir: Path | None = None,
) -> dict | None:
    """Attach a document. Returns its dict (with content), or
    None when the chat is missing/foreign (chat scope)."""
    if scope not in (SCOPE_CHAT, SCOPE_GLOBAL):
        raise ValueError(f"unknown scope: {scope!r}")
    if not await _verify_scope(session, user_id, scope, chat_id):
        return None
    doc = {
        "id": str(uuid.uuid4()),
        "scope": scope,
        "chat_id": chat_id if scope == SCOPE_CHAT else None,
        "name": _validate_name(name),
        "content_type": _validate_content_type(content_type),
        "content": _validate_content(content),
        "enabled": _validate_enabled(enabled),
        "priority": _validate_priority(priority),
        "created_at": _utcnow_iso(),
        "updated_at": _utcnow_iso(),
    }
    existing = _list_scope_docs(user_id, scope, chat_id, base_dir)
    if len(existing) >= MAX_DOCS_PER_SCOPE:
        raise ValueError(f"data bank is full ({MAX_DOCS_PER_SCOPE} documents per scope)")
    _write_document(user_id, doc, base_dir)
    if scope == SCOPE_CHAT:
        await _record_event(session, chat_id, EVENT_DATABANK_ATTACHED, data={
            "document_id": doc["id"], "name": doc["name"], "scope": scope,
            "tokens": document_tokens(doc),
        })
        await session.commit()
    return document_to_dict(doc, include_content=True)


async def list_documents(
    session: AsyncSession,
    user_id: str,
    scope: str,
    chat_id: str | None = None,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """List one scope's documents (metadata, no content) plus
    that scope's own budget accounting. For chat scope the
    accounting covers chat documents only; the combined
    chat+global prompt view is :func:`load_prompt_selection`."""
    if scope not in (SCOPE_CHAT, SCOPE_GLOBAL):
        raise ValueError(f"unknown scope: {scope!r}")
    if not await _verify_scope(session, user_id, scope, chat_id):
        return None
    docs = _list_scope_docs(user_id, scope, chat_id, base_dir)
    budget = _read_budget(user_id, scope, chat_id, base_dir)
    selection = select_documents(docs, budget)
    return {
        "documents": [document_to_dict(d) for d in docs],
        "accounting": accounting_to_dict(selection),
    }


async def get_document(
    session: AsyncSession,
    user_id: str,
    scope: str,
    chat_id: str | None,
    doc_id: str,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    if scope not in (SCOPE_CHAT, SCOPE_GLOBAL):
        raise ValueError(f"unknown scope: {scope!r}")
    _validate_doc_id(doc_id)
    if not await _verify_scope(session, user_id, scope, chat_id):
        return None
    path = _doc_path(user_id, scope, chat_id, doc_id, base_dir)
    if not path.exists():
        return None
    doc = _read_document_at(path, user_id, scope, chat_id if scope == SCOPE_CHAT else None)
    return document_to_dict(doc, include_content=True)


async def update_document(
    session: AsyncSession,
    user_id: str,
    scope: str,
    chat_id: str | None,
    doc_id: str,
    *,
    name=None,
    content=None,
    content_type=None,
    enabled=None,
    priority=None,
    base_dir: Path | None = None,
) -> dict | None:
    """Update the given fields (None = leave unchanged)."""
    if scope not in (SCOPE_CHAT, SCOPE_GLOBAL):
        raise ValueError(f"unknown scope: {scope!r}")
    _validate_doc_id(doc_id)
    if not await _verify_scope(session, user_id, scope, chat_id):
        return None
    path = _doc_path(user_id, scope, chat_id, doc_id, base_dir)
    if not path.exists():
        return None
    doc = _read_document_at(path, user_id, scope, chat_id if scope == SCOPE_CHAT else None)
    if name is not None:
        doc["name"] = _validate_name(name)
    if content is not None:
        doc["content"] = _validate_content(content)
    if content_type is not None:
        doc["content_type"] = _validate_content_type(content_type)
    if enabled is not None:
        doc["enabled"] = _validate_enabled(enabled)
    if priority is not None:
        doc["priority"] = _validate_priority(priority)
    doc["updated_at"] = _utcnow_iso()
    _write_document(user_id, doc, base_dir)
    if scope == SCOPE_CHAT:
        await _record_event(session, chat_id, EVENT_DATABANK_UPDATED, data={
            "document_id": doc["id"], "name": doc["name"], "scope": scope,
            "tokens": document_tokens(doc),
        })
        await session.commit()
    return document_to_dict(doc, include_content=True)


async def detach_document(
    session: AsyncSession,
    user_id: str,
    scope: str,
    chat_id: str | None,
    doc_id: str,
    *,
    base_dir: Path | None = None,
) -> bool | None:
    """Detach (delete) one document. True = deleted; False = no
    such document; None = chat missing/foreign (chat scope)."""
    if scope not in (SCOPE_CHAT, SCOPE_GLOBAL):
        raise ValueError(f"unknown scope: {scope!r}")
    _validate_doc_id(doc_id)
    if not await _verify_scope(session, user_id, scope, chat_id):
        return None
    path = _doc_path(user_id, scope, chat_id, doc_id, base_dir)
    if not path.exists():
        return False
    doc = _read_document_at(path, user_id, scope, chat_id if scope == SCOPE_CHAT else None)
    path.unlink()
    if scope == SCOPE_CHAT:
        await _record_event(session, chat_id, EVENT_DATABANK_DETACHED, data={
            "document_id": doc["id"], "name": doc["name"], "scope": scope,
        })
        await session.commit()
    return True


async def get_budget(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    if not await _verify_scope(session, user_id, SCOPE_CHAT, chat_id):
        return None
    return {"budget_tokens": _read_budget(user_id, SCOPE_CHAT, chat_id, base_dir)}


async def set_budget(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    budget_tokens,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    if not await _verify_scope(session, user_id, SCOPE_CHAT, chat_id):
        return None
    budget = _validate_budget(budget_tokens)
    _write_budget(user_id, SCOPE_CHAT, chat_id, budget, base_dir)
    await _record_event(session, chat_id, EVENT_DATABANK_BUDGET_CHANGED, data={
        "budget_tokens": budget,
    })
    await session.commit()
    return {"budget_tokens": budget}


async def load_prompt_selection(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    counter=None,
    base_dir: Path | None = None,
) -> Selection | None:
    """The combined chat+global selection for one chat's prompt,
    governed by the CHAT's declared budget. None when the chat
    is missing/foreign."""
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    docs = _scope_docs_with_globals(user_id, SCOPE_CHAT, chat_id, base_dir)
    budget = _read_budget(user_id, SCOPE_CHAT, chat_id, base_dir)
    return select_documents(docs, budget, counter)


def remove_chat_databank(user_id: str, chat_id: str, base_dir: Path | None = None) -> None:
    """Remove a deleted chat's data-bank directory (its chat-scope
    documents + settings). Global documents are untouched: they
    belong to the owner, not the chat. Mirrors
    ``checkpoints.remove_chat_checkpoints``."""
    directory = _scope_dir(user_id, SCOPE_CHAT, chat_id, base_dir)
    if directory.is_dir():
        shutil.rmtree(directory)

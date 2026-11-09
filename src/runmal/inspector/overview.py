"""Composed Inspector overview (P-203): one read-only
document per owned chat answering "what inspection truth
exists for this chat, from which banked source, in what
state".

The roadmap names Part XIII's Inspector only as a
CONSUMER of three already-banked surfaces: P-043
activation inspection (POST /lorebooks/{book_id}/inspect,
schema runmal-p043-activation-inspection-v1), P-059
prompt preview / inspect (POST /debug/prompt-inspect and
POST /debug/prompt-preview) and P-075 message provenance
(GET /chats/{chat_id}/provenance). This service joins
those three plus the chat's scenario-binding state into
ONE schema-versioned document. It CALLS the banked
surfaces - it never re-implements any of them (the P-059
one-source-of-truth rule, generalised).

Honesty law (the P-075 idiom, transposed):

- every section carries a status from the closed set
  available / empty / not_applicable / unavailable, plus
  a plain ``reason`` string whenever it is not available;
- the provenance section carries the P-075 chat summary
  VERBATIM from the banked read - counts and statuses
  only, exactly what P-075 itself already returns, no
  per-message records and no new content exposure;
- a section whose upstream read fails reads
  ``unavailable`` + the reason, never a faked empty;
- the overview composes NO prompt and runs NO
  activation inspection inside this read: composition
  and activation live behind the banked POST roads
  (which may consume probability rolls), and a GET must
  not spend rolls as a side effect. The prompt and lore
  sections therefore state availability and POINT at
  those roads instead of running them;
- the scenario section carries the binding record's own
  summary shape (identity + counts read from the record
  itself) - seeded content stays on the banked
  single-read road;
- nothing is persisted, cached or written: the document
  is assembled fresh from the banked truth on each call.
"""

from __future__ import annotations

import copy

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chats_service
from runmal.inspector import OVERVIEW_SCHEMA
from runmal.lorebooks import scopes as lore_scopes
from runmal.lorebooks.inspector import INSPECT_SCHEMA as LORE_INSPECT_SCHEMA
from runmal.scenarios import binding as scenario_binding

__all__ = [
    "GENERATED_FROM",
    "SECTION_STATUSES",
    "build_overview",
]

#: The banked sources this document is composed from, in
#: the fixed order the document declares.
GENERATED_FROM = ["P-043", "P-059", "P-075", "scenario bindings"]

#: The closed section-status vocabulary (P-075 idiom).
SECTION_STATUSES = frozenset(
    {"available", "empty", "not_applicable", "unavailable"}
)

#: The banked prompt roads the prompt section points at.
#: Composition stays behind these POST roads; the
#: overview itself never composes.
PROMPT_ROADS = {
    "inspect": {
        "method": "POST",
        "path": "/api/v1/debug/prompt-inspect",
    },
    "preview": {
        "method": "POST",
        "path": "/api/v1/debug/prompt-preview",
    },
}


def _section(status: str, *, reason: str | None = None, **fields) -> dict:
    """One overview section: a closed-vocabulary status, a
    plain reason when not available, then the section's
    own banked fields."""
    doc = {"status": status, "reason": reason}
    doc.update(fields)
    return doc


async def _provenance_section(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict:
    """P-075: the chat summary carried VERBATIM from the
    banked provenance read (totals, by origin, by model
    status). A chat with no messages is honestly empty; a
    failed read is unavailable, never a faked empty."""
    try:
        payload = await chats_service.list_chat_provenance(
            session, user_id, chat_id
        )
    except Exception as exc:  # upstream read failed: say so
        return _section(
            "unavailable", reason=f"provenance read failed: {exc}"
        )
    if payload is None:
        return _section(
            "unavailable",
            reason="provenance read found no owned chat",
        )
    summary = copy.deepcopy(payload["summary"])
    if summary.get("total", 0) == 0:
        return _section(
            "empty",
            reason="the chat has no messages, so no provenance exists yet",
            summary=summary,
        )
    return _section("available", summary=summary)


def _prompt_section() -> dict:
    """P-059: availability + pointers only. The overview
    does NOT compose or render a prompt - composition
    stays behind the banked POST roads named here, so a
    read never composes as a side effect."""
    return _section(
        "available",
        roads=copy.deepcopy(PROMPT_ROADS),
        note=(
            "Prompt inspection and preview for this chat live on the "
            "banked POST roads named here; this overview composes no "
            "prompt of its own, so reading it has no side effects."
        ),
    )


async def _lore_section(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict:
    """P-043: the lorebooks bound to this chat, resolved
    through the banked P-040 layered scope resolution,
    each with a pointer at the banked P-043 inspect road.
    The overview does NOT run an activation inspection
    itself - an inspection may consume probability rolls,
    and a read must not spend them."""
    try:
        resolved = await lore_scopes.resolve_scoped_books(
            session, user_id, chat_id=chat_id
        )
    except Exception as exc:  # upstream read failed: say so
        return _section(
            "unavailable", reason=f"scoped lore resolution failed: {exc}"
        )
    if resolved is None:
        return _section(
            "unavailable",
            reason="scoped lore resolution found no owned chat",
        )
    books = []
    for kind in lore_scopes.LAYER_ORDER:
        for book in resolved.layers.get(kind, ()):
            books.append(
                {
                    "lorebook_id": book.book_id,
                    "scope_kind": book.scope_kind,
                    "via": book.via,
                    "inspect": {
                        "method": "POST",
                        "path": f"/api/v1/lorebooks/{book.book_id}/inspect",
                        "schema": LORE_INSPECT_SCHEMA,
                    },
                }
            )
    if not books:
        return _section(
            "empty",
            reason=(
                "no lorebooks are scoped to this chat (the global, "
                "character, persona and chat layers are all empty)"
            ),
            books=[],
        )
    return _section("available", books=books)


def _scenario_section(user_id: str, chat_id: str, bindings_store) -> dict:
    """Scenario binding state from the banked binding
    store: the record's own summary shape (identity +
    counts) when bound; an honest empty when unbound; no
    flag values or seeded content are carried here."""
    try:
        record = scenario_binding.get_binding(bindings_store, user_id, chat_id)
    except Exception as exc:  # upstream read failed: say so
        return _section(
            "unavailable", reason=f"scenario binding read failed: {exc}"
        )
    if record is None:
        return _section(
            "empty",
            reason="no scenario is bound to this chat",
            bound=False,
        )
    return _section("available", bound=True, binding=record.summary())


async def build_overview(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    *,
    bindings_store=None,
) -> dict | None:
    """The composed Inspector overview for one owned chat.

    Returns None when the chat is missing or foreign (the
    router maps that to the house 404 idiom; existence
    never leaks). Pure read: assembles the document from
    the banked surfaces and persists nothing.
    """
    chat = await chats_service.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if bindings_store is None:
        bindings_store = scenario_binding.ScenarioBindingStore(
            scenario_binding.bindings_path()
        )
    return {
        "schema": OVERVIEW_SCHEMA,
        "chat_id": chat_id,
        "generated_from": list(GENERATED_FROM),
        "sections": {
            "provenance": await _provenance_section(session, user_id, chat_id),
            "prompt": _prompt_section(),
            "lore_activation": await _lore_section(session, user_id, chat_id),
            "scenario": _scenario_section(user_id, chat_id, bindings_store),
        },
    }

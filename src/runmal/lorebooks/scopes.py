"""P-040 lore scopes -- global + persona + chat lore, layered.

A lorebook may be SCOPED: assigned to a layer of a chat's world.

- ``global`` -- the world layer: the book applies to every chat
  the owner runs. Its owner id is the empty string.
- ``character`` -- the book is assigned to one character and
  applies whenever that character is in play.
- ``persona`` -- the book is assigned to the persona the user is
  playing AS in a chat. In Runmal a chat's persona IS a character
  (``chats.character_id``, switched by ``set_chat_persona``), so a
  persona scope's owner id is a character id -- the same id space
  as the character layer, a different role: character scopes dress
  the character being talked TO, persona scopes dress the
  character being talked AS.
- ``chat`` -- the book is bound to one chat and applies only
  there.

Activation gathers the layers in declared order -- world
(global) -> character -> persona -> chat -- mirroring the
mirrors' layering (world info, then the character's own book,
then what the user brings as their persona, then what this one
chat has pinned). Each layer carries its OWN token budget: the
budget caps the layer's total included lore for the tick, on top
of each book's own ``token_budget`` (which still applies inside
that book's preview). A layer budget of None is unlimited; a
layer budget of 0 mutes the layer (it contributes nothing, and
says so in the report) -- deliberately unlike per-book budgets,
which require >= 1: a scope is a dial the user may turn fully
off.

The P-039 character-book binding participates without a scope
row: the bound book IS the character layer's first book, with an
unlimited layer assignment of its own (its budget contribution
is the binding's, recorded as scope kind ``character`` with
``via == "binding"``). A book with an explicit character scope
row for the same character AND a binding keeps both assignments
only if they name different books; the same book named twice in
one layer is one book.

One book, one layer per tick: if the same lorebook is assigned
in several layers that all apply, only the MOST SPECIFIC layer's
assignment survives (chat beats persona beats character beats
global); the shadowed assignments are reported, never silently
dropped and never double-counted.

Books with no scope rows at all are untouched by this module:
they behave exactly as before P-040 (the caller names them
explicitly, e.g. prompt-inspect's ``lorebook_ids``).

The pure helpers in this module (vocabulary, budget normaliser,
layer resolution) carry no DB, I/O or randomness. The async
service functions below them are ownership-scoped like the rest
of the lorebook services: a book, character or chat the caller
does not own is indistinguishable from one that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import (
    Character,
    CharacterBookBinding,
    Chat,
    Lorebook,
    LorebookScope,
    LoreEntry,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.windows import ScanSettings

__all__ = [
    "SCOPE_GLOBAL",
    "SCOPE_CHARACTER",
    "SCOPE_PERSONA",
    "SCOPE_CHAT",
    "SCOPE_KINDS",
    "LAYER_ORDER",
    "GLOBAL_OWNER_ID",
    "check_scope_kind",
    "normalise_scope_kind",
    "normalise_scope_budget",
    "ScopedBook",
    "ResolvedLayers",
    "resolve_layers",
    "scope_to_dict",
    "assign_scope",
    "unassign_scope",
    "list_book_scopes",
    "list_scopes",
    "resolve_scoped_books",
    "layered_preview",
]

SCOPE_GLOBAL = "global"
SCOPE_CHARACTER = "character"
SCOPE_PERSONA = "persona"
SCOPE_CHAT = "chat"

SCOPE_KINDS = frozenset(
    {SCOPE_GLOBAL, SCOPE_CHARACTER, SCOPE_PERSONA, SCOPE_CHAT}
)

#: Declared composition order: world -> character -> persona -> chat.
LAYER_ORDER = (SCOPE_GLOBAL, SCOPE_CHARACTER, SCOPE_PERSONA, SCOPE_CHAT)

#: The owner id of the global layer (it has no owner row).
GLOBAL_OWNER_ID = ""

_LAYER_RANK = {kind: rank for rank, kind in enumerate(LAYER_ORDER)}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def check_scope_kind(value) -> str:
    """Strict validation: return ``value`` if it is a canonical scope kind.

    Mirrors the strict checkers in lorebooks/binding.py: no
    defaulting, no case folding, no stripping -- anything that is
    not exactly one of the canonical names raises ValueError.
    """
    if isinstance(value, str) and value in SCOPE_KINDS:
        return value
    raise ValueError(
        f"invalid scope kind: {value!r} (valid: {sorted(SCOPE_KINDS)})"
    )


def normalise_scope_kind(value) -> str:
    """Tolerant scope-kind normaliser: None -> global, else strict-ish.

    Strings are stripped and lower-cased before lookup; a string
    that does not name a scope kind (and any non-string other than
    None) raises ValueError rather than silently inventing one.
    """
    if value is None:
        return SCOPE_GLOBAL
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in SCOPE_KINDS:
            return candidate
    raise ValueError(
        f"invalid scope kind: {value!r} (valid: {sorted(SCOPE_KINDS)})"
    )


def normalise_scope_budget(value) -> int | None:
    """Normalise a per-scope (layer) token budget.

    None -> None (unlimited). An int >= 0 is kept as-is -- 0 is a
    REAL budget here: it mutes the layer. Bools, negatives, floats
    and non-numbers raise ValueError; nothing is silently coerced.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"scope budget must be an int >= 0 or None: {value!r}"
        )
    if value < 0:
        raise ValueError(f"scope budget must be >= 0 or None: {value!r}")
    return value


def check_scope_owner(scope_kind, owner_id) -> str:
    """Validate + normalise the owner id for a scope kind. PURE.

    Global scopes take no owner (any supplied owner is refused,
    not ignored -- a global row carrying a chat id would be a
    lie). Every other kind requires a non-empty string owner id.
    Returns the canonical owner id (``""`` for global).
    """
    kind = check_scope_kind(scope_kind)
    if kind == SCOPE_GLOBAL:
        if owner_id is None or owner_id == "":
            return GLOBAL_OWNER_ID
        raise ValueError("global scope takes no owner_id")
    if isinstance(owner_id, str) and owner_id:
        return owner_id
    raise ValueError(f"{kind} scope requires a non-empty owner_id")


@dataclass(frozen=True)
class ScopedBook:
    """One book's assignment to one layer for one tick. PURE."""

    book_id: str
    scope_kind: str
    owner_id: str = GLOBAL_OWNER_ID
    budget: int | None = None
    position: int = 0
    via: str = "scope"  # "scope" (a lorebook_scopes row) | "binding" (P-039)


@dataclass(frozen=True)
class ResolvedLayers:
    """The layered resolution of a set of scoped books. PURE.

    ``layers`` maps every kind in LAYER_ORDER to the tuple of
    ScopedBook assignments surviving in that layer, in
    deterministic order (position, then book id). ``shadowed``
    reports every assignment dropped because the same book
    survived in a more specific layer.
    """

    layers: dict
    shadowed: tuple


def resolve_layers(scoped_books) -> ResolvedLayers:
    """Resolve scoped books into ordered layers. PURE, deterministic.

    Dedupe rule: a book id present in several layers survives
    ONLY in the most specific one (latest in LAYER_ORDER); the
    other assignments are reported in ``shadowed`` as
    ``{book_id, kept_scope, dropped_scope}`` in deterministic
    order. The same book twice in the SAME layer collapses to
    its first assignment in (position, book_id) order. Inputs
    are never mutated.
    """
    normalised: list[ScopedBook] = []
    for book in scoped_books or []:
        kind = check_scope_kind(book.scope_kind)
        normalised.append(
            ScopedBook(
                book_id=str(book.book_id),
                scope_kind=kind,
                owner_id=str(book.owner_id or GLOBAL_OWNER_ID),
                budget=normalise_scope_budget(book.budget),
                position=int(book.position or 0),
                via=str(book.via or "scope"),
            )
        )

    kept_scope_by_book: dict[str, str] = {}
    for book in normalised:
        current = kept_scope_by_book.get(book.book_id)
        if current is None or _LAYER_RANK[book.scope_kind] > _LAYER_RANK[current]:
            kept_scope_by_book[book.book_id] = book.scope_kind

    layers: dict[str, list[ScopedBook]] = {kind: [] for kind in LAYER_ORDER}
    shadowed: list[dict] = []
    seen_in_layer: set[tuple[str, str]] = set()
    ordered = sorted(
        normalised,
        key=lambda b: (_LAYER_RANK[b.scope_kind], b.position, b.book_id),
    )
    for book in ordered:
        kept = kept_scope_by_book[book.book_id]
        if book.scope_kind != kept:
            shadowed.append(
                {
                    "book_id": book.book_id,
                    "kept_scope": kept,
                    "dropped_scope": book.scope_kind,
                }
            )
            continue
        key = (book.scope_kind, book.book_id)
        if key in seen_in_layer:
            continue
        seen_in_layer.add(key)
        layers[book.scope_kind].append(book)
    return ResolvedLayers(
        layers={kind: tuple(books) for kind, books in layers.items()},
        shadowed=tuple(shadowed),
    )


def scope_to_dict(scope, lorebook=None) -> dict:
    """JSON-shaped scope record, with lorebook summary when given."""
    result = {
        "id": getattr(scope, "id", None),
        "lorebook_id": getattr(scope, "lorebook_id", None),
        "scope_kind": getattr(scope, "scope_kind", None),
        "owner_id": getattr(scope, "owner_id", None),
        "token_budget": getattr(scope, "token_budget", None),
        "position": getattr(scope, "position", None),
        "created_at": _iso(getattr(scope, "created_at", None)),
        "updated_at": _iso(getattr(scope, "updated_at", None)),
    }
    if lorebook is not None:
        from runmal.lorebooks.service import lorebook_to_dict

        result["lorebook"] = lorebook_to_dict(lorebook)
    return result


async def _get_owned_book(session: AsyncSession, user_id: str, book_id: str):
    result = await session.execute(
        select(Lorebook).where(Lorebook.id == book_id, Lorebook.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _get_owned_character(session: AsyncSession, user_id: str, character_id: str):
    result = await session.execute(
        select(Character).where(
            Character.id == character_id,
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _get_owned_chat(session: AsyncSession, user_id: str, chat_id: str):
    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _check_owner_exists(
    session: AsyncSession, user_id: str, scope_kind: str, owner_id: str
) -> None:
    """Raise ValueError when a non-global scope's owner is not owned."""
    if scope_kind == SCOPE_GLOBAL:
        return
    if scope_kind == SCOPE_CHAT:
        if await _get_owned_chat(session, user_id, owner_id) is None:
            raise ValueError("chat not found")
    else:  # character + persona owners are characters
        if await _get_owned_character(session, user_id, owner_id) is None:
            raise ValueError("character not found")


async def assign_scope(
    session: AsyncSession,
    user_id: str,
    lorebook_id: str,
    scope_kind,
    owner_id=None,
    token_budget=None,
    position=None,
    *,
    commit: bool = True,
):
    """Assign (or re-assign) a lorebook to a scope layer, upserting.

    The unique key is (lorebook, scope kind, owner): re-assigning
    the same triple updates budget/position in place. Raises
    ValueError("lorebook not found") / ("character not found") /
    ("chat not found") for unowned targets, and ValueError for an
    invalid kind, owner or budget.
    """
    kind = check_scope_kind(scope_kind)
    owner = check_scope_owner(kind, owner_id)
    budget = normalise_scope_budget(token_budget)
    if position is None:
        position_value = 0
    elif isinstance(position, bool) or not isinstance(position, int):
        raise ValueError(f"scope position must be an int: {position!r}")
    else:
        position_value = position
    book = await _get_owned_book(session, user_id, lorebook_id)
    if book is None:
        raise ValueError("lorebook not found")
    await _check_owner_exists(session, user_id, kind, owner)
    result = await session.execute(
        select(LorebookScope).where(
            LorebookScope.lorebook_id == lorebook_id,
            LorebookScope.scope_kind == kind,
            LorebookScope.owner_id == owner,
        )
    )
    scope = result.scalar_one_or_none()
    if scope is None:
        scope = LorebookScope(
            user_id=user_id,
            lorebook_id=lorebook_id,
            scope_kind=kind,
            owner_id=owner,
            token_budget=budget,
            position=position_value,
        )
        session.add(scope)
    else:
        scope.token_budget = budget
        scope.position = position_value
        scope.updated_at = _now()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return scope


async def unassign_scope(
    session: AsyncSession,
    user_id: str,
    lorebook_id: str,
    scope_kind,
    owner_id=None,
    *,
    commit: bool = True,
) -> bool:
    """Delete one scope assignment; False when none existed.

    The lorebook itself survives untouched. An unowned lorebook
    is indistinguishable from a missing assignment (False).
    """
    kind = check_scope_kind(scope_kind)
    owner = check_scope_owner(kind, owner_id)
    if await _get_owned_book(session, user_id, lorebook_id) is None:
        return False
    result = await session.execute(
        delete(LorebookScope).where(
            LorebookScope.lorebook_id == lorebook_id,
            LorebookScope.scope_kind == kind,
            LorebookScope.owner_id == owner,
            LorebookScope.user_id == user_id,
        )
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return (result.rowcount or 0) > 0


async def list_book_scopes(session: AsyncSession, user_id: str, lorebook_id: str):
    """All scope assignments of an owned book, in layer order.

    None when the book is not owned by the caller.
    """
    if await _get_owned_book(session, user_id, lorebook_id) is None:
        return None
    result = await session.execute(
        select(LorebookScope)
        .where(
            LorebookScope.lorebook_id == lorebook_id,
            LorebookScope.user_id == user_id,
        )
        .order_by(LorebookScope.scope_kind, LorebookScope.owner_id)
    )
    rows = list(result.scalars().all())
    rows.sort(key=lambda s: (_LAYER_RANK[s.scope_kind], s.position, s.owner_id))
    return rows


async def list_scopes(
    session: AsyncSession, user_id: str, scope_kind, owner_id=None
) -> list:
    """All scope assignments in one layer for one owner, in order."""
    kind = check_scope_kind(scope_kind)
    owner = check_scope_owner(kind, owner_id)
    result = await session.execute(
        select(LorebookScope)
        .where(
            LorebookScope.user_id == user_id,
            LorebookScope.scope_kind == kind,
            LorebookScope.owner_id == owner,
        )
        .order_by(LorebookScope.position, LorebookScope.lorebook_id)
    )
    return list(result.scalars().all())


async def resolve_scoped_books(
    session: AsyncSession,
    user_id: str,
    *,
    chat_id: str | None = None,
    character_id: str | None = None,
    persona_character_id: str | None = None,
) -> ResolvedLayers | None:
    """Gather every scoped book applying to a context. PURE-ish read.

    Context resolution: an explicit ``character_id`` /
    ``persona_character_id`` wins; otherwise both default from
    the chat (its character is both the character in play and
    the persona in play until a caller says otherwise -- the
    persona switch IS ``set_chat_persona`` writing
    ``chat.character_id``). Returns None when a named chat is
    not owned by the caller. The P-039 binding for the resolved
    character contributes its book as a ``via="binding"``
    character-layer assignment.
    """
    chat = None
    if chat_id is not None:
        chat = await _get_owned_chat(session, user_id, chat_id)
        if chat is None:
            return None
    if character_id is None and chat is not None:
        character_id = chat.character_id
    if persona_character_id is None:
        persona_character_id = character_id

    scoped: list[ScopedBook] = []

    async def _collect(kind: str, owner: str) -> None:
        for row in await list_scopes(session, user_id, kind, owner):
            scoped.append(
                ScopedBook(
                    book_id=row.lorebook_id,
                    scope_kind=kind,
                    owner_id=owner,
                    budget=row.token_budget,
                    position=row.position,
                    via="scope",
                )
            )

    await _collect(SCOPE_GLOBAL, GLOBAL_OWNER_ID)
    if character_id is not None:
        binding_result = await session.execute(
            select(CharacterBookBinding).where(
                CharacterBookBinding.character_id == character_id
            )
        )
        binding = binding_result.scalar_one_or_none()
        if binding is not None:
            scoped.append(
                ScopedBook(
                    book_id=binding.lorebook_id,
                    scope_kind=SCOPE_CHARACTER,
                    owner_id=character_id,
                    budget=None,
                    position=-1,
                    via="binding",
                )
            )
        await _collect(SCOPE_CHARACTER, character_id)
    if persona_character_id is not None:
        await _collect(SCOPE_PERSONA, persona_character_id)
    if chat_id is not None:
        await _collect(SCOPE_CHAT, chat_id)
    return resolve_layers(scoped)


async def _list_entries_service_order(session: AsyncSession, book_id: str) -> list:
    result = await session.execute(
        select(LoreEntry)
        .where(LoreEntry.lorebook_id == book_id)
        .order_by(LoreEntry.priority.desc(), LoreEntry.created_at)
    )
    return list(result.scalars().all())


def _apply_layer_budget(preview: dict, layer_budget: int | None) -> dict:
    """Trim one layer's composed preview to its scope budget. PURE-ish.

    ``preview`` is a merged preview_activation-shaped dict whose
    rows already passed each book's own budget. The layer budget
    is a second, independent gate: included rows are packed in
    row order (the preview's deterministic order) until the
    budget is spent; rows that no longer fit become
    ``discarded`` with ``discard_reason == "scope_over_budget"``
    and the preview's ``tokens_used`` is recomputed. A budget of
    0 discards every included row. The dict is updated in place
    and returned.
    """
    if layer_budget is None:
        preview["scope_budget"] = None
        return preview
    used = 0
    for row in preview.get("entries", []):
        if row.get("status") != "included":
            continue
        tokens = row.get("tokens") or 0
        if tokens > layer_budget - used:
            row["status"] = "discarded"
            row["discard_reason"] = "scope_over_budget"
            continue
        used += tokens
    preview["tokens_used"] = used
    preview["scope_budget"] = layer_budget
    return preview


async def layered_preview(
    session: AsyncSession,
    user_id: str,
    *,
    chat_id: str | None = None,
    character_id: str | None = None,
    persona_character_id: str | None = None,
    messages,
    seed=None,
    external_context=None,
) -> dict | None:
    """Preview activation across every applicable lore layer.

    None when a named chat is not owned. Otherwise returns a
    dict with one preview per layer (each the merged
    preview_activation shape for that layer's books, trimmed by
    the layer's scope budgets) plus a ``scopes`` summary: per
    layer, the books, the layer budget actually enforced (the
    MINIMUM of the layer's assignments' budgets -- one dial per
    layer, the strictest assignment wins, so a layer can never
    silently exceed a budget any of its assignments declared),
    tokens used, and included/discarded counts -- the composed
    result inspectable per scope. ``shadowed`` reports books
    dropped from a less specific layer.
    """
    resolved = await resolve_scoped_books(
        session,
        user_id,
        chat_id=chat_id,
        character_id=character_id,
        persona_character_id=persona_character_id,
    )
    if resolved is None:
        return None

    layers_out: dict[str, dict] = {}
    scopes_summary: list[dict] = []
    total_tokens = 0
    for kind in LAYER_ORDER:
        books = resolved.layers[kind]
        if not books:
            continue
        declared = [b.budget for b in books if b.budget is not None]
        layer_budget = min(declared) if declared else None
        merged_rows: list[dict] = []
        book_dicts: list[dict] = []
        layer_scan_depth = 4
        for assignment in books:
            book = await _get_owned_book(session, user_id, assignment.book_id)
            if book is None:
                continue
            entries = await _list_entries_service_order(session, book.id)
            settings = ScanSettings.from_book(book)
            single = preview_activation(
                entries,
                list(messages),
                settings.scan_depth,
                book.token_budget,
                seed=seed,
                scan_mode=settings.scan_mode,
                scan_external_context=settings.scan_external_context,
                external_context=list(external_context or []),
            )
            layer_scan_depth = settings.scan_depth
            for row in single["entries"]:
                row = dict(row)
                row["lorebook_id"] = book.id
                row["scope"] = kind
                row["scope_owner_id"] = assignment.owner_id
                row["scope_via"] = assignment.via
                merged_rows.append(row)
            book_dicts.append(
                {
                    "lorebook_id": book.id,
                    "name": book.name,
                    "via": assignment.via,
                    "budget": assignment.budget,
                    "position": assignment.position,
                }
            )
        layer_preview = _apply_layer_budget(
            {
                "scan_depth": layer_scan_depth,
                "token_budget": layer_budget,
                "tokens_used": sum(
                    (r.get("tokens") or 0)
                    for r in merged_rows
                    if r.get("status") == "included"
                ),
                "entries": merged_rows,
            },
            layer_budget,
        )
        layers_out[kind] = layer_preview
        included = sum(
            1 for r in merged_rows if r.get("status") == "included"
        )
        scopes_summary.append(
            {
                "scope": kind,
                "owner_id": books[0].owner_id if books else GLOBAL_OWNER_ID,
                "books": book_dicts,
                "budget": layer_budget,
                "tokens_used": layer_preview["tokens_used"],
                "included": included,
                "discarded": sum(
                    1 for r in merged_rows if r.get("status") == "discarded"
                ),
            }
        )
        total_tokens += layer_preview["tokens_used"]
    return {
        "layered": True,
        "layer_order": list(LAYER_ORDER),
        "chat_id": chat_id,
        "character_id": character_id,
        "persona_character_id": persona_character_id,
        "scopes": scopes_summary,
        "layers": layers_out,
        "shadowed": list(resolved.shadowed),
        "tokens_used": total_tokens,
    }

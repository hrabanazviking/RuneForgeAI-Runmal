"""Prompt manager (P-049): the prompt as an editable structure.

Until P-049 the composer's block order was fixed baseline data
(:data:`runmal.prompt.slots.BASELINE_ORDER`): a preset could move an
individual slot by assigning it a different ``order``, but the BLOCKS
of the prompt -- system, persona, lore, memory, author's note,
examples, history -- were not a first-class thing a user could see,
reorder, or switch off.

The prompt manager makes them one. A :class:`PromptLayout` is data:
an ordered tuple of :class:`PromptBlock` rows, one per block, each
carrying only its ``enabled`` flag. The layout is validated and
normalised by :func:`layout_from_data` (the same shape the API
accepts and returns), and :func:`apply_layout` rewrites a slot list
through it before composition:

- a slot whose block is disabled is dropped (and returned, so the
  caller can record it in the Prompt Trace as a discard with reason
  ``prompt_manager_disabled`` -- a disabled block never reaches the
  composed prompt, not even a ``required`` one: the manager is the
  user's explicit instruction, and it outranks the slot's default
  required flag);
- a kept slot's ``order`` becomes its block's position, so
  reordering the layout changes assembly order in the composer;
- slots whose kind belongs to no managed block (today:
  ``post_history``, P-057's future citizen) keep baseline-relative
  order after the managed blocks -- the manager governs what it
  names and leaves the rest exactly where the baseline put it
  relative to the whole;
- depth-injected slots (S206) keep the splice contract: a depth slot
  is composed only when the composer reaches it AFTER the history
  slot has been emitted, so when a depth slot's own block sits
  before the history block (and history is enabled) its order is
  raised to just after the history block; when its block already
  sits at or after history its block order stands. If history is
  disabled the depth slot is a plain slot in block order -- there
  is nothing to splice into and the composer falls through to
  plain emission, as it already does for a history-less prompt.

The default layout lists the blocks in baseline order with every
block enabled, and applying it reproduces the baseline assembly
exactly (position-faithful blocks, see BLOCK_KINDS). With no layout
in play the pipeline is exactly the pre-P-049 pipeline.

Scope: P-049 ships the layout as data -- validated here, supplied
through the inspector API, honoured by the composer. Persisting a
layout per owner or per chat is a named follow-up slice that owns
its own migration; nothing in P-049 pretends to store one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from runmal.prompt.slots import BASELINE_INDEX, Slot

#: Prompt blocks in baseline order: block name -> the slot kinds it
#: governs. Lore and memory each occupy TWO baseline positions, so
#: each position is its own block (``lore_before`` / ``lore_after``,
#: ``memory_nucleus`` / ``memory_retrieved``): blocks are contiguous
#: by construction, and a grouped lore/memory block could not
#: reproduce the baseline interleaving (memory_nucleus < lore_before
#: < memory_retrieved; history < lore_after). Position-faithful
#: blocks make the default layout a true identity. A UI may present
#: the pairs as one lore / one memory group; the data stays honest.
BLOCK_KINDS: dict[str, tuple[str, ...]] = {
    "system": ("main_system",),
    "persona": ("persona",),
    "memory_nucleus": ("memory_nucleus",),
    "lore_before": ("lore_before",),
    "memory_retrieved": ("memory_retrieved",),
    "examples": ("examples",),
    "history": ("history",),
    "lore_after": ("lore_after",),
    "authors_note": ("authors_note",),
}

#: Block names in baseline (default layout) order.
BLOCK_ORDER: tuple[str, ...] = tuple(
    sorted(
        BLOCK_KINDS,
        key=lambda name: min(BASELINE_INDEX[k] for k in BLOCK_KINDS[name]),
    )
)

_KIND_TO_BLOCK: dict[str, str] = {
    kind: block for block, kinds in BLOCK_KINDS.items() for kind in kinds
}

#: Trace discard reason for slots a disabled block removed.
DISABLED_REASON = "prompt_manager_disabled"


@dataclass(frozen=True)
class PromptBlock:
    block: str
    enabled: bool = True


@dataclass(frozen=True)
class PromptLayout:
    blocks: tuple[PromptBlock, ...]

    def position(self, block: str) -> int | None:
        for i, row in enumerate(self.blocks):
            if row.block == block:
                return i
        return None

    def is_enabled(self, block: str) -> bool:
        for row in self.blocks:
            if row.block == block:
                return row.enabled
        return True


def default_layout() -> PromptLayout:
    """The baseline layout: every block enabled, in baseline order."""
    return PromptLayout(tuple(PromptBlock(name) for name in BLOCK_ORDER))


def layout_from_data(data: object) -> PromptLayout:
    """Validate + normalise layout data (API / stored shape).

    Accepts a list of ``{"block": name, "enabled": bool}`` entries
    (``enabled`` optional, default true) or a dict with a ``blocks``
    list of the same. Unknown or duplicated blocks raise ValueError.
    Blocks the data does not mention are filled in from the default
    layout at their baseline-relative positions, so a partial layout
    (e.g. only the blocks a user actually moved) still denotes a
    complete structure. (A future block -- P-057's post_history is
    the known candidate -- must not invalidate layouts written
    before it existed, which is why missing blocks fill rather
    than fail.)
    """
    if isinstance(data, dict):
        data = data.get("blocks")
    if not isinstance(data, list):
        raise ValueError("prompt layout must be a list of blocks")
    seen: list[PromptBlock] = []
    names: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("prompt layout entries must be objects")
        name = entry.get("block")
        if name not in BLOCK_KINDS:
            raise ValueError(f"unknown prompt block: {name!r}")
        if name in names:
            raise ValueError(f"duplicate prompt block: {name!r}")
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"prompt block {name!r} enabled must be a boolean")
        names.add(name)
        seen.append(PromptBlock(name, enabled))
    if not seen:
        raise ValueError("prompt layout must name at least one block")
    # Fill missing blocks at baseline-relative positions: insert each
    # missing block just before the first present block that follows
    # it in the default order (or at the end when none follows).
    filled = list(seen)
    present = {row.block for row in filled}
    for missing in BLOCK_ORDER:
        if missing in present:
            continue
        at = len(filled)
        for i, row in enumerate(filled):
            if BLOCK_ORDER.index(row.block) > BLOCK_ORDER.index(missing):
                at = i
                break
        filled.insert(at, PromptBlock(missing))
        present.add(missing)
    return PromptLayout(tuple(filled))


def layout_to_data(layout: PromptLayout) -> dict:
    return {
        "blocks": [
            {"block": row.block, "enabled": row.enabled} for row in layout.blocks
        ]
    }


def block_for_kind(kind: str) -> str | None:
    """The managed block governing a slot kind, or None."""
    return _KIND_TO_BLOCK.get(kind)


def apply_layout(
    slots: list[Slot], layout: PromptLayout
) -> tuple[list[Slot], list[Slot]]:
    """Rewrite ``slots`` through ``layout`` for the composer.

    Returns ``(kept, dropped)``: a kept slot's ``order`` becomes
    ``block_position * 100 + baseline_index(kind)`` (the baseline
    index is data, never encounter order, so same-block kinds keep
    their baseline relation and same-kind slots fall to the
    composer's own ``(order, -priority, id)`` tie-break); dropped
    slots are the disabled blocks' slots, in input order, so the
    caller can record them in the trace.

    Depth slots (S206): the composer splices a depth slot only when
    it reaches it after the history slot, so a depth slot's order is
    ``max(assigned, history_assigned + 10)`` -- keyed on the history
    slot's ASSIGNED order, not its block position alone. When the
    history block is disabled there is no history slot and no
    adjustment: the depth slot falls through to plain emission, as
    the composer already treats a history-less prompt.

    Unmanaged kinds (today: ``post_history``, P-057's future
    citizen) form the unmanaged tail:
    ``len(blocks) * 100 + baseline_index(kind)``.
    """
    from runmal.prompt.slots import BASELINE_ORDER as _BO

    span = 100
    history_pos = layout.position("history")
    history_enabled = layout.is_enabled("history")
    history_assigned = (
        history_pos * span + BASELINE_INDEX["history"]
        if history_enabled and history_pos is not None
        else None
    )
    kept: list[Slot] = []
    dropped: list[Slot] = []
    for slot in slots:
        block = _KIND_TO_BLOCK.get(slot.kind)
        if block is None:
            kept.append(
                replace(
                    slot,
                    order=len(layout.blocks) * span
                    + BASELINE_INDEX.get(slot.kind, len(_BO)),
                )
            )
            continue
        if not layout.is_enabled(block):
            dropped.append(slot)
            continue
        pos = layout.position(block)
        assert pos is not None  # normalised layouts name every block
        order = pos * span + BASELINE_INDEX.get(slot.kind, 0)
        if slot.depth is not None and history_assigned is not None:
            order = max(order, history_assigned + 10)
        kept.append(replace(slot, order=order))
    return kept, dropped

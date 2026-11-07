"""Post-history instructions (P-057) -- clean-room.

Post-history instructions are a per-chat (or per-character) instruction
placed at the very end of the prompt: after the conversation history,
baseline-last. The position IS the contract -- there is no depth and
no frequency by design, because the instruction's meaning comes from
being the last word the model reads before it replies.

Neutral name note: some other prompt systems call this position the
"jailbreak" position. Runmal names it neutrally -- post-history
instructions -- because the position is a general prompt-assembly
contract, not a bypass technique.

This module is the instructions as data -- nothing more, nothing less:

- :class:`PostHistoryInstructions` is the validated value object: the
  instruction text, whether it is ``enabled``, and the ``role`` its
  slot is spoken in.
- :func:`instructions_from_data` / :func:`instructions_to_data` are
  the strict boundary with stored / supplied data (the shape
  persisted as one JSON document in ``chats.post_history_json``,
  migration 0035 PROVISIONAL): unknown keys and wrong types all
  raise ``ValueError`` -- malformed instructions are refused, never
  repaired silently and never partially applied.
- :func:`slot_for` builds the composer's slot when -- and only
  when -- the instructions have content (:func:`has_content`): kind
  ``post_history`` at its baseline position, so the existing prompt
  manager (P-049, extended by P-057) and composer do the rest. An
  empty, whitespace-only, or disabled instruction produces no slot.

Clean-room: written for P-057 from the Runmal slot/composer
contracts alone; no third-party post-history implementation was
copied or consulted.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.prompt.slots import Slot, make_slot

#: Roles a post-history slot may speak in (mirrors the slot contract).
VALID_ROLES = frozenset({"system", "user", "assistant"})

#: Sources a post-history slot may come from.
VALID_SOURCES = frozenset({"chat", "character"})

_FIELDS = frozenset({"text", "enabled", "role"})


@dataclass(frozen=True)
class PostHistoryInstructions:
    """Post-history instructions, as validated data."""

    text: str = ""
    enabled: bool = True
    role: str = "system"

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("post-history text must be a string")
        if not isinstance(self.enabled, bool):
            raise ValueError("post-history enabled must be a bool")
        if self.role not in VALID_ROLES:
            raise ValueError(f"invalid post-history role: {self.role!r}")


def instructions_from_data(data: object) -> PostHistoryInstructions:
    """Validate stored / supplied ``data`` into instructions.

    ``None`` means nothing was stored: the default (empty)
    instructions. Anything else must be a dict carrying only known
    keys; missing keys take the dataclass defaults.
    """
    if data is None:
        return PostHistoryInstructions()
    if not isinstance(data, dict):
        raise ValueError("post-history data must be an object or None")
    unknown = set(data) - _FIELDS
    if unknown:
        raise ValueError(f"unknown post-history keys: {sorted(unknown)}")
    # Each present value is type-checked here so the error names the
    # field; PostHistoryInstructions.__post_init__ re-checks the same
    # invariants for instructions built directly in code.
    if "text" in data and not isinstance(data["text"], str):
        raise ValueError("post-history text must be a string")
    if "enabled" in data and not isinstance(data["enabled"], bool):
        raise ValueError("post-history enabled must be a bool")
    if "role" in data and data["role"] not in VALID_ROLES:
        raise ValueError(f"invalid post-history role: {data['role']!r}")
    return PostHistoryInstructions(
        text=data.get("text", ""),
        enabled=data.get("enabled", True),
        role=data.get("role", "system"),
    )


def instructions_to_data(ph: PostHistoryInstructions) -> dict:
    """Serialise ``ph`` with all three keys, always."""
    return {
        "text": ph.text,
        "enabled": ph.enabled,
        "role": ph.role,
    }


def has_content(ph: PostHistoryInstructions) -> bool:
    """True only when enabled and text is non-blank."""
    return ph.enabled and bool(ph.text.strip())


def slot_for(ph: PostHistoryInstructions, source: str) -> Slot | None:
    """The composer's post-history slot for ``ph``, or None.

    ``source`` must be one of :data:`VALID_SOURCES` (``chat`` or
    ``character``); anything else raises ``ValueError``. Returns
    ``None`` when the instructions have no content.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"invalid post-history source: {source!r}")
    if not has_content(ph):
        return None
    return make_slot(
        "post_history",
        ph.role,
        ph.text,
        id=f"post_history/{source}",
        provenance=f"{source}:post_history",
    )

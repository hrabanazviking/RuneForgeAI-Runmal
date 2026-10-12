"""Card prompt fields -> structured slots (S110).

A slot manifest is an ordered mapping of prompt-slot name to macro-substituted
text. Only prompt-bearing card fields become slots. Creator metadata
(creator_notes, tags, creator) stays metadata per S105 unless a future spec
opts it in; first_mes / alternate_greetings are greetings, not prompt slots;
character_book / extensions belong to future lorebook handling.
"""

from __future__ import annotations

import re

from runmal.cards.models import CharacterCard

#: Canonical slot order, also the render order.
SLOT_ORDER = (
    "system_prompt",
    "description",
    "personality",
    "scenario",
    "mes_example",
    "post_history_instructions",
)

_MACRO_RE = re.compile(r"\{\{\s*(char|user|original)\s*\}\}", re.IGNORECASE)


def substitute_macros(text: str, char_name: str, user_name: str = "User") -> str:
    """Expand ``{{char}}``, ``{{user}}`` and ``{{original}}`` (case-insensitive).

    ``{{original}}`` expands to the text as it was before substitution
    (self-reference for wrapper patterns). Unknown ``{{...}}`` macros are
    left untouched.
    """

    def _replace(match: re.Match) -> str:
        name = match.group(1).lower()
        if name == "char":
            return char_name
        if name == "user":
            return user_name
        return text  # {{original}}

    return _MACRO_RE.sub(_replace, text)


def build_slot_manifest(card: CharacterCard, user_name: str = "User") -> dict[str, str]:
    """Build the ordered slot manifest for a card. Empty slots are omitted."""
    manifest: dict[str, str] = {}
    for slot in SLOT_ORDER:
        raw = getattr(card, slot, "")
        if raw:
            manifest[slot] = substitute_macros(raw, card.name, user_name)
    return manifest


def render_system_prompt(manifest: dict[str, str]) -> str:
    """Concatenate manifest slots in canonical order, blank-line separated."""
    return "\n\n".join(manifest[slot] for slot in SLOT_ORDER if slot in manifest)

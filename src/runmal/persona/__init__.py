"""Persona prompt assembly (S110)."""

from runmal.persona.slots import (
    SLOT_ORDER,
    build_slot_manifest,
    render_system_prompt,
    substitute_macros,
)

__all__ = [
    "SLOT_ORDER",
    "build_slot_manifest",
    "render_system_prompt",
    "substitute_macros",
]

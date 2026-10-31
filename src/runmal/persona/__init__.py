"""Persona prompt assembly (S110) + user-persona file interop (P-018)."""

from runmal.persona.interop import (
    DESCRIPTION_POSITIONS,
    PersonaParseError,
    UserPersona,
    export_persona,
    parse_persona,
    persona_description_slot,
)
from runmal.persona.slots import (
    SLOT_ORDER,
    build_slot_manifest,
    render_system_prompt,
    substitute_macros,
)

__all__ = [
    "DESCRIPTION_POSITIONS",
    "PersonaParseError",
    "SLOT_ORDER",
    "UserPersona",
    "build_slot_manifest",
    "export_persona",
    "parse_persona",
    "persona_description_slot",
    "render_system_prompt",
    "substitute_macros",
]

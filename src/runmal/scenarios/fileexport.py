"""Scenario file export (P-026): Voxta-shaped scenario files out.

Clean-room basis: the exchanged shape is as recorded in P-003's
census (VX-28..VX-44 + VX-60) from public documentation only.
No SillyTavern/Voxta source was read.

Export to the Voxta shape is a raw overlay (INV-009): the emitted
object starts from a deep copy of the scenario's ``raw`` mapping
-- unknown-but-valid fields survive verbatim, in their original
key position -- and overlays the normalized known fields under
the write rules below, in a fixed order, so keys the raw file did
not carry append deterministically. Nothing is fabricated: a
field the source file did not carry, and the typed record does
not carry either, is not invented on export.

Elements that could not be mapped natively on import are handed
back verbatim: each value in ``unmappable_values``, keyed by its
report path, overwrites the raw copy with the original JSON
value. Book-level unknowns in ``extra`` ride back as well, under
``setdefault`` so the overlaid known fields win.

The native shape is the clean-data rule instead: it carries only
typed fields plus ``extra``, in a fixed full set -- no ``raw``,
no import ``report`` and no ``unmappable_values``.
"""

from __future__ import annotations

import copy
import json

from .filemodels import FLOW_TO_VOXTA, STYLE_TO_VOXTA, ScenarioFile


def _put(obj, raw, primary, alias, value, emit):
    """Write ``value`` under the primary or aliased key.

    If ``alias`` is present in ``raw`` and ``primary`` is not, the
    alias spelling the source file used is kept; otherwise the
    primary spelling is written when it was in ``raw`` or ``emit``
    says the typed record carries a value worth writing.
    """
    if alias is not None and alias in raw and primary not in raw:
        obj[alias] = value
    elif primary in raw or emit:
        obj[primary] = value


def _role_object(role) -> dict:
    """One role: raw overlaid with the normalized fields."""
    raw = role.raw or {}
    obj: dict = copy.deepcopy(role.raw) if role.raw else {}
    if "role" in raw and "name" not in raw:
        obj["role"] = role.name
    else:
        obj["name"] = role.name
    if "character" in raw and "characterName" not in raw:
        obj["character"] = role.character_name
    elif "characterName" in raw or role.character_name:
        obj["characterName"] = role.character_name
    obj["enabledOnStart"] = role.enabled_on_start
    obj["canSpeak"] = role.can_speak
    return obj


def _bootstrap_message_object(msg) -> dict:
    """One bootstrap message: raw overlaid with normalized fields."""
    raw = msg.raw or {}
    obj: dict = copy.deepcopy(msg.raw) if msg.raw else {}
    obj["text"] = msg.text
    if "type" in raw:
        obj["type"] = msg.kind
    elif "kind" in raw or msg.kind != "message":
        obj["kind"] = msg.kind
    if "role" in raw or msg.role:
        obj["role"] = msg.role
    return obj


def _context_object(ctx) -> dict:
    """One context block: raw overlaid with normalized fields."""
    raw = ctx.raw or {}
    obj: dict = copy.deepcopy(ctx.raw) if ctx.raw else {}
    if "key" in raw or ctx.key:
        obj["key"] = ctx.key
    if "content" in raw and "text" not in raw:
        obj["content"] = ctx.text
    elif "text" in raw or ctx.text:
        obj["text"] = ctx.text
    if "condition" in raw or ctx.condition:
        obj["condition"] = ctx.condition
    if "role" in raw or ctx.role:
        obj["role"] = ctx.role
    if "position" in raw or ctx.position:
        obj["position"] = ctx.position
    return obj


def export_voxta(scenario: ScenarioFile) -> dict:
    """Export a ScenarioFile as a Voxta-shaped JSON object.

    Starts from a deep copy of ``scenario.raw`` and overlays the
    normalized fields in a fixed order; keys already in raw keep
    their position and new keys append in overlay order.
    """
    raw = scenario.raw or {}
    obj: dict = copy.deepcopy(scenario.raw) if scenario.raw else {}
    # 1. name: always.
    obj["name"] = scenario.name
    # 2. description.
    _put(obj, raw, "description", None, scenario.description, bool(scenario.description))
    # 3. scenario_text.
    _put(obj, raw, "scenario", "scenarioText", scenario.scenario_text, bool(scenario.scenario_text))
    # 4. flow: always.
    _put(obj, raw, "chatFlow", "flow", FLOW_TO_VOXTA.get(scenario.flow, "Chat"), True)
    # 5. style: only when the typed style carries a value; an
    # empty style with a raw key leaves raw's value unchanged.
    if scenario.style:
        _put(obj, raw, "chatStyle", "style", STYLE_TO_VOXTA.get(scenario.style), True)
    # 6. template_text.
    _put(obj, raw, "scenarioTemplate", "template", scenario.template_text, bool(scenario.template_text))
    # 7. system_prompt.
    system_prompt_raw = raw.get("systemPrompt")
    if isinstance(system_prompt_raw, dict):
        system_prompt_obj = copy.deepcopy(system_prompt_raw)
        system_prompt_obj["text"] = scenario.system_prompt_text
        if scenario.system_prompt_mode or "mode" in system_prompt_raw:
            system_prompt_obj["mode"] = scenario.system_prompt_mode
        obj["systemPrompt"] = system_prompt_obj
    elif scenario.system_prompt_mode:
        obj["systemPrompt"] = {
            "text": scenario.system_prompt_text,
            "mode": scenario.system_prompt_mode,
        }
    elif "systemPrompt" in raw or scenario.system_prompt_text:
        obj["systemPrompt"] = scenario.system_prompt_text
    # 8. roles.
    if scenario.roles or "roles" in raw:
        obj["roles"] = [_role_object(role) for role in scenario.roles]
    # 9. bootstrap_messages.
    _put(
        obj,
        raw,
        "bootstrapMessages",
        "bootstrap",
        [_bootstrap_message_object(msg) for msg in scenario.bootstrap_messages],
        bool(scenario.bootstrap_messages),
    )
    # 10. impersonation.
    impersonation_raw = raw.get("impersonation")
    if isinstance(impersonation_raw, dict):
        impersonation_obj = copy.deepcopy(impersonation_raw)
        impersonation_obj["name"] = scenario.impersonation_name
        if scenario.impersonation_description or "description" in impersonation_raw:
            impersonation_obj["description"] = scenario.impersonation_description
        obj["impersonation"] = impersonation_obj
    elif scenario.impersonation_description:
        obj["impersonation"] = {
            "name": scenario.impersonation_name,
            "description": scenario.impersonation_description,
        }
    elif scenario.impersonation_name or "impersonation" in raw:
        obj["impersonation"] = scenario.impersonation_name
    # 11. narrator.
    narrator_raw = raw.get("narrator")
    if isinstance(narrator_raw, dict):
        narrator_obj = copy.deepcopy(narrator_raw)
        narrator_obj["name"] = scenario.narrator_name
        if scenario.narrator_voice or "voice" in narrator_raw:
            narrator_obj["voice"] = scenario.narrator_voice
        obj["narrator"] = narrator_obj
    elif scenario.narrator_voice:
        obj["narrator"] = {
            "name": scenario.narrator_name,
            "voice": scenario.narrator_voice,
        }
    elif scenario.narrator_name or "narrator" in raw:
        obj["narrator"] = scenario.narrator_name
    # 12. memory_book_refs.
    if scenario.memory_book_refs:
        if "memoryBooks" in raw:
            obj["memoryBooks"] = list(scenario.memory_book_refs)
        elif "memory_books" in raw:
            obj["memory_books"] = list(scenario.memory_book_refs)
        elif "books" in raw:
            obj["books"] = list(scenario.memory_book_refs)
        else:
            obj["memoryBooks"] = list(scenario.memory_book_refs)
    # 13. initial_flags.
    if "flags" in raw:
        flags_key = "flags"
    elif "initialFlags" in raw:
        flags_key = "initialFlags"
    else:
        flags_key = "flags"
    if scenario.initial_flags or flags_key in raw:
        if isinstance(raw.get(flags_key), list):
            obj[flags_key] = list(scenario.initial_flags.keys())
        else:
            obj[flags_key] = copy.deepcopy(scenario.initial_flags)
    # 14. initial_variables.
    _put(
        obj,
        raw,
        "variables",
        "initialVariables",
        copy.deepcopy(scenario.initial_variables),
        bool(scenario.initial_variables),
    )
    # 15. contexts.
    if scenario.contexts or "contexts" in raw:
        obj["contexts"] = [_context_object(ctx) for ctx in scenario.contexts]
    # 16. parent_ref.
    _put(obj, raw, "parent", "parentScenario", scenario.parent_ref, bool(scenario.parent_ref))
    # 17. thumbnail_ref.
    _put(obj, raw, "thumbnail", None, scenario.thumbnail_ref, bool(scenario.thumbnail_ref))
    # 18. Unmappable hand-back, verbatim.
    for path, value in scenario.unmappable_values.items():
        obj[path] = copy.deepcopy(value)
    # 19. Book-level unknowns.
    for key, value in scenario.extra.items():
        obj.setdefault(key, copy.deepcopy(value))
    # 20. A Voxta file carries no native source-format marker.
    obj.pop("source_format", None)
    return obj


def export_native(scenario: ScenarioFile) -> dict:
    """Export a ScenarioFile in Rúnmál's native shape.

    Clean data only: typed fields plus ``extra``, always the full
    fixed set -- no ``raw``, no report, no unmappable values.
    """
    obj: dict = copy.deepcopy(scenario.extra)
    obj["source_format"] = "native"
    obj["name"] = scenario.name
    obj["description"] = scenario.description
    obj["scenario_text"] = scenario.scenario_text
    obj["flow"] = scenario.flow
    obj["style"] = scenario.style
    obj["template_text"] = scenario.template_text
    obj["system_prompt_text"] = scenario.system_prompt_text
    obj["system_prompt_mode"] = scenario.system_prompt_mode
    obj["roles"] = [
        {
            "name": role.name,
            "character_name": role.character_name,
            "enabled_on_start": role.enabled_on_start,
            "can_speak": role.can_speak,
        }
        for role in scenario.roles
    ]
    obj["bootstrap_messages"] = [
        {
            "kind": msg.kind,
            "text": msg.text,
            "role": msg.role,
        }
        for msg in scenario.bootstrap_messages
    ]
    obj["impersonation_name"] = scenario.impersonation_name
    obj["impersonation_description"] = scenario.impersonation_description
    obj["narrator_name"] = scenario.narrator_name
    obj["narrator_voice"] = scenario.narrator_voice
    obj["memory_book_refs"] = list(scenario.memory_book_refs)
    obj["initial_flags"] = copy.deepcopy(scenario.initial_flags)
    obj["initial_variables"] = copy.deepcopy(scenario.initial_variables)
    obj["contexts"] = [
        {
            "key": ctx.key,
            "text": ctx.text,
            "condition": ctx.condition,
            "role": ctx.role,
            "position": ctx.position,
        }
        for ctx in scenario.contexts
    ]
    obj["parent_ref"] = scenario.parent_ref
    obj["thumbnail_ref"] = scenario.thumbnail_ref
    return obj


def export_voxta_bytes(scenario: ScenarioFile) -> bytes:
    """Export as Voxta-shaped JSON bytes."""
    return json.dumps(export_voxta(scenario), ensure_ascii=False, indent=2).encode("utf-8")


def export_native_bytes(scenario: ScenarioFile) -> bytes:
    """Export as native JSON bytes."""
    return json.dumps(export_native(scenario), ensure_ascii=False, indent=2).encode("utf-8")

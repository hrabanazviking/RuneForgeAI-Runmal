"""Scenario-library logic for the desktop shell (R-12) — Qt-free.

A scenario definition is a document: authored text fields the
editor owns, plus structured sections (roles, bootstrap
messages, contexts, initial flags/variables, memory-book refs)
the editor carries verbatim and names — the R-09 bundle /
R-10 lorebook compose discipline. Bindings attach a definition
to an owned EMPTY chat (the engine seeds the chat's opening
lines from the definition's bootstrap messages).
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import RunmalClient, ScenarioView

#: The authored text fields, in form order: (key, label, long?).
AUTHORED_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("name", "Name", False),
    ("description", "Description", True),
    ("scenario_text", "Scenario", True),
    ("flow", "Flow", False),
    ("style", "Style", False),
    ("template_text", "Template", True),
    ("system_prompt_text", "System prompt", True),
    ("system_prompt_mode", "System prompt mode", False),
    ("impersonation_name", "Impersonation name", False),
    ("impersonation_description", "Impersonation description", True),
    ("narrator_name", "Narrator name", False),
    ("narrator_voice", "Narrator voice", False),
)

#: Structured sections carried verbatim, with count labels.
CARRIED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("roles", "roles"),
    ("bootstrap_messages", "bootstrap messages"),
    ("contexts", "contexts"),
    ("memory_book_refs", "memory-book refs"),
)


def scenario_line(scenario: ScenarioView) -> str:
    bits = [scenario.name or "(unnamed scenario)"]
    roles = scenario.raw.get("role_count")
    if isinstance(roles, int) and roles:
        bits.append(f"{roles} role(s)")
    if scenario.raw.get("is_favourite"):
        bits.append("★ favourite")
    tags = scenario.raw.get("tags") or []
    if tags:
        bits.append("tags: " + ", ".join(str(t) for t in tags))
    return " · ".join(bits)


def carried_words(definition: dict[str, Any]) -> str:
    """Name the structured sections a save will carry verbatim."""
    parts: list[str] = []
    for key, label in CARRIED_SECTIONS:
        value = definition.get(key)
        if isinstance(value, list) and value:
            parts.append(f"{label}: {len(value)}")
    flags = definition.get("initial_flags")
    if isinstance(flags, dict) and flags:
        parts.append(f"initial flags: {len(flags)}")
    variables = definition.get("initial_variables")
    if isinstance(variables, dict) and variables:
        parts.append(f"initial variables: {len(variables)}")
    if not parts:
        return "No structured sections (roles, bootstrap, contexts) yet."
    return "Carried unchanged on save — " + " · ".join(parts)


def compose_definition(
    stored: dict[str, Any], values: dict[str, str]
) -> dict[str, Any]:
    """Lay the form's authored fields over the stored definition."""
    document = dict(stored)
    for key, _label, _long in AUTHORED_FIELDS:
        document[key] = values.get(key, "")
    return document


def binding_words(binding: dict[str, Any]) -> str:
    if not binding:
        return "This chat has no scenario bound."
    name = binding.get("definition_name") or binding.get("name") or ""
    state = binding.get("state") or ""
    bits = ["Bound scenario: " + (name or str(binding.get("definition_id", "")))]
    if state:
        bits.append(f"state: {state}")
    seeded = binding.get("seeded_messages")
    if isinstance(seeded, int):
        bits.append(f"{seeded} opening line(s) seeded")
    return " · ".join(bits)


def bindings_lines(bindings: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for binding in bindings:
        name = (
            binding.get("definition_name")
            or binding.get("name")
            or binding.get("definition_id", "")
        )
        chat = binding.get("chat_id", "")
        state = binding.get("state") or (
            "stale" if binding.get("definition_exists") is False else ""
        )
        line = f"{name} → chat {str(chat)[:8]}…"
        if state:
            line += f" · {state}"
        lines.append(line)
    return lines


class ScenarioFlow:
    """The Scenarios dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def library(self, *, q: str = "") -> list[ScenarioView]:
        return self._client.list_scenarios(q=q)

    def get(self, definition_id: str) -> ScenarioView:
        return self._client.get_scenario(definition_id)

    def create(self, definition: dict[str, Any]) -> ScenarioView:
        return self._client.create_scenario(definition)

    def save(
        self, scenario: ScenarioView, definition: dict[str, Any]
    ) -> ScenarioView:
        return self._client.update_scenario(scenario.id, definition)

    def delete(self, scenario: ScenarioView) -> None:
        self._client.delete_scenario(scenario.id)

    def duplicate(self, scenario: ScenarioView) -> ScenarioView:
        return self._client.duplicate_scenario(scenario.id)

    def set_favourite(self, scenario: ScenarioView, value: bool) -> None:
        self._client.set_scenario_favourite(scenario.id, value)

    def set_tags(self, scenario: ScenarioView, tags: list[str]) -> None:
        self._client.set_scenario_tags(scenario.id, tags)

    def bind(self, scenario: ScenarioView, chat_id: str) -> dict[str, Any]:
        return self._client.bind_scenario(scenario.id, chat_id)

    def unbind(self, chat_id: str) -> None:
        self._client.unbind_scenario(chat_id)

    def chat_binding(self, chat_id: str) -> dict[str, Any]:
        try:
            return self._client.get_chat_binding(chat_id)
        except Exception:  # noqa: BLE001 - unbound chats may 404
            return {}

    def bindings(self) -> list[dict[str, Any]]:
        return self._client.list_scenario_bindings()

    def import_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.import_scenario(payload)

    def export_file(
        self, scenario: ScenarioView, *, fmt: str = "native"
    ) -> dict[str, Any]:
        return self._client.export_scenario(scenario.definition, fmt=fmt)

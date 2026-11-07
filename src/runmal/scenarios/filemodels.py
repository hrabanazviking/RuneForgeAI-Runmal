"""Typed contract for scenario-file interop (P-026).

Clean-room basis = P-003 Voxta census VX-28..VX-44 + VX-60
from public documentation. This module is the *contract*
every other P-026 module builds on — the typed scenario
file, its roles, bootstrap messages and contexts, the
import report, and the typed parse error. It performs
no I/O, and imports nothing from other runmal modules,
so importers, exporters and the bridge can all depend on
it without a cycle. No SillyTavern/Voxta source was read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Source format markers.
SOURCE_VOXTA = "voxta"
SOURCE_NATIVE = "native"

#: Maximum accepted scenario-file size, in bytes.
MAX_SCENARIO_BYTES = 8 * 1024 * 1024

#: Native flow / style vocabularies.
FLOWS = ("chat", "story")
STYLES = ("companion", "roleplay", "storytelling", "assistant")

#: Native flow / style spellings -> Voxta spellings.
FLOW_TO_VOXTA = {"chat": "Chat", "story": "Story"}
STYLE_TO_VOXTA = {
    "companion": "Companion",
    "roleplay": "Roleplay",
    "storytelling": "Storytelling",
    "assistant": "Assistant",
}

#: Bootstrap message kinds this slice maps natively.
BOOTSTRAP_KINDS = (
    "char",
    "user",
    "role",
    "event",
    "story",
    "note",
    "secret",
    "instructions",
    "message",
)

#: Kinds that cannot be mapped natively; elements carrying
#: one of these are reported as unmappable and their original
#: values are carried for hand-back on export.
KIND_SCRIPTING = "scripting"
KIND_EVENT = "event"
KIND_ACTION = "action"
KIND_TOOL = "tool"
KIND_BUTTON = "button"
KIND_CONTROL = "control"
KIND_HUD = "hud_widget"
KIND_APP = "app_config"
KIND_ASSET = "asset_bytes"
KIND_TEMPLATE = "template_evaluation"


class ScenarioParseError(ValueError):
    """A scenario file import failed for a clear, testable reason."""


@dataclass
class ScenarioRole:
    """One role (character slot) declared by a scenario.

    `raw` always holds the complete original mapping so
    unknown-but-valid fields survive.
    """

    name: str
    character_name: str = ""
    enabled_on_start: bool = True
    can_speak: bool = True
    raw: dict = field(default_factory=dict, compare=False)


@dataclass
class BootstrapMessage:
    """One bootstrap message seeded by a scenario."""

    kind: str = "message"
    text: str = ""
    role: str = ""
    raw: dict = field(default_factory=dict, compare=False)


@dataclass
class ScenarioContext:
    """One conditional context block carried by a scenario."""

    key: str = ""
    text: str = ""
    condition: str = ""
    role: str = ""
    position: str = ""
    raw: dict = field(default_factory=dict, compare=False)


@dataclass
class UnmappableElement:
    """One element that could not be mapped natively."""

    path: str
    kind: str
    reason: str
    name: str = ""


@dataclass
class ScenarioImportReport:
    """Account of an import: what was mapped, what was
    carried verbatim, what was unmappable, and warnings."""

    source_format: str = SOURCE_VOXTA
    mapped: list[str] = field(default_factory=list)
    carried: list[str] = field(default_factory=list)
    unmappable: list[UnmappableElement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_unmappable(self) -> bool:
        """True when any element could not be mapped."""
        return bool(self.unmappable)

    def to_dict(self) -> dict:
        """This report as plain data."""
        return {
            "source_format": self.source_format,
            "mapped": list(self.mapped),
            "carried": list(self.carried),
            "unmappable": [
                {
                    "path": element.path,
                    "kind": element.kind,
                    "name": element.name,
                    "reason": element.reason,
                }
                for element in self.unmappable
            ],
            "warnings": list(self.warnings),
        }


@dataclass
class ScenarioFile:
    """A whole scenario file, normalized.

    `raw` always holds the complete original mapping so
    unknown-but-valid fields survive; `extra` carries
    book-level unknowns, and `unmappable_values` carries
    the original JSON value for each unmappable element
    (keyed by its report path) so export can hand it back.
    `report` is the import report when this file came from
    an import; it is `None` for a natively authored file.
    """

    name: str
    description: str = ""
    scenario_text: str = ""
    flow: str = "chat"
    style: str = ""
    template_text: str = ""
    system_prompt_text: str = ""
    system_prompt_mode: str = ""
    roles: list[ScenarioRole] = field(default_factory=list)
    bootstrap_messages: list[BootstrapMessage] = field(default_factory=list)
    impersonation_name: str = ""
    impersonation_description: str = ""
    narrator_name: str = ""
    narrator_voice: str = ""
    memory_book_refs: list[str] = field(default_factory=list)
    initial_flags: dict = field(default_factory=dict)
    initial_variables: dict = field(default_factory=dict)
    contexts: list[ScenarioContext] = field(default_factory=list)
    parent_ref: str = ""
    thumbnail_ref: str = ""
    extra: dict = field(default_factory=dict)
    # path -> original JSON value for each unmappable element,
    # so export can hand it back
    unmappable_values: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict, compare=False)
    source_format: str = SOURCE_VOXTA
    report: ScenarioImportReport | None = field(default=None, compare=False)

"""Scenarios: file interop (P-026) + stored definitions (P-131).

- ``filemodels`` / ``fileimport`` / ``fileexport`` — the
  P-026 contract: Voxta-shaped and native scenario files
  parsed defensively, reported honestly (unmappable
  machinery is reported, never faked), and re-exported.
- ``store`` — scenario definitions as first-class,
  persistent, owner-scoped citizens: the versioned JSON
  store (``scenarios.json``), validation at the store
  door through the P-026 parser, and the import report
  carried with each record as data (P-131, Part IX
  opener, DERIVED scope).
- ``storedexport`` — stored-definition file export: a
  stored definition handed back as a file through P-026's
  own exporters, with an honest report naming whatever
  cannot round-trip (P-133, Part IX, DERIVED scope).
- ``binding`` — scenario-to-chat binding: the versioned
  JSON binding store (``scenario_bindings.json``), the
  materialisation plan, and the bind service that seeds
  a definition's bootstrap lines and initial state into
  an empty chat (P-132, Part IX, DERIVED scope).
- ``router`` — the HTTP roads: the stateless P-026
  import/export roads plus the P-131 definition CRUD
  roads on the same /scenarios prefix.
"""

from runmal.scenarios.binding import (
    BINDINGS_FILENAME,
    BINDINGS_VERSION,
    BindingConflictError,
    BindingNotFoundError,
    ScenarioBinding,
    ScenarioBindingError,
    ScenarioBindingStore,
    bind_scenario,
    bindings_path,
    get_binding,
    plan_materialisation,
    unbind,
)
from runmal.scenarios.fileexport import (
    export_native,
    export_native_bytes,
    export_voxta,
    export_voxta_bytes,
)
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import (
    BOOTSTRAP_KINDS,
    FLOW_TO_VOXTA,
    FLOWS,
    KIND_ACTION,
    KIND_APP,
    KIND_ASSET,
    KIND_BUTTON,
    KIND_CONTROL,
    KIND_EVENT,
    KIND_HUD,
    KIND_SCRIPTING,
    KIND_TEMPLATE,
    KIND_TOOL,
    MAX_SCENARIO_BYTES,
    SOURCE_NATIVE,
    SOURCE_VOXTA,
    STYLE_TO_VOXTA,
    STYLES,
    BootstrapMessage,
    ScenarioContext,
    ScenarioFile,
    ScenarioImportReport,
    ScenarioParseError,
    ScenarioRole,
    UnmappableElement,
)
from runmal.scenarios.storedexport import (
    DEFAULT_FORMAT,
    FORMATS as EXPORT_FORMATS,
    StoredExportError,
    export_stored_definition,
    scenario_file_from_stored,
)
from runmal.scenarios.store import (
    DEFINITIONS_FILENAME,
    DEFINITIONS_VERSION,
    ScenarioDefinition,
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)

__all__ = [
    "BOOTSTRAP_KINDS",
    "BINDINGS_FILENAME",
    "BINDINGS_VERSION",
    "DEFINITIONS_FILENAME",
    "DEFINITIONS_VERSION",
    "FLOWS",
    "FLOW_TO_VOXTA",
    "KIND_ACTION",
    "KIND_APP",
    "KIND_ASSET",
    "KIND_BUTTON",
    "KIND_CONTROL",
    "KIND_EVENT",
    "KIND_HUD",
    "KIND_SCRIPTING",
    "KIND_TEMPLATE",
    "KIND_TOOL",
    "MAX_SCENARIO_BYTES",
    "SOURCE_NATIVE",
    "SOURCE_VOXTA",
    "STYLES",
    "STYLE_TO_VOXTA",
    "BootstrapMessage",
    "BindingConflictError",
    "ScenarioContext",
    "ScenarioDefinition",
    "ScenarioFile",
    "ScenarioImportReport",
    "ScenarioParseError",
    "ScenarioRole",
    "ScenarioBinding",
    "ScenarioBindingError",
    "ScenarioBindingStore",
    "ScenarioStore",
    "BindingNotFoundError",
    "ScenarioStoreError",
    "StoredExportError",
    "UnmappableElement",
    "DEFAULT_FORMAT",
    "EXPORT_FORMATS",
    "bind_scenario",
    "bindings_path",
    "definitions_path",
    "export_stored_definition",
    "scenario_file_from_stored",
    "get_binding",
    "plan_materialisation",
    "unbind",
    "export_native",
    "export_native_bytes",
    "export_voxta",
    "export_voxta_bytes",
    "parse_scenario_file",
]

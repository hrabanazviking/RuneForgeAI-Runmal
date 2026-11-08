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
- ``router`` — the HTTP roads: the stateless P-026
  import/export roads plus the P-131 definition CRUD
  roads on the same /scenarios prefix.
"""

from runmal.scenarios.fileexport import (
    export_native,
    export_native_bytes,
    export_voxta,
    export_voxta_bytes,
)
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import (
    BOOTSTRAP_KINDS,
    FLOWS,
    FLOW_TO_VOXTA,
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
    STYLES,
    STYLE_TO_VOXTA,
    BootstrapMessage,
    ScenarioContext,
    ScenarioFile,
    ScenarioImportReport,
    ScenarioParseError,
    ScenarioRole,
    UnmappableElement,
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
    "ScenarioContext",
    "ScenarioDefinition",
    "ScenarioFile",
    "ScenarioImportReport",
    "ScenarioParseError",
    "ScenarioRole",
    "ScenarioStore",
    "ScenarioStoreError",
    "UnmappableElement",
    "definitions_path",
    "export_native",
    "export_native_bytes",
    "export_voxta",
    "export_voxta_bytes",
    "parse_scenario_file",
]

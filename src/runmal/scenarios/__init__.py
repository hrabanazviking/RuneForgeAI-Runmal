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
  opener, DERIVED scope); its duplication verb clones
  one definition faithfully under a fresh id — report
  and source format preserved exactly, the name under
  the characters S303 " (copy)" law (P-137, Part IX,
  DERIVED scope).
- ``storedexport`` — stored-definition file export: a
  stored definition handed back as a file through P-026's
  own exporters, with an honest report naming whatever
  cannot round-trip (P-133, Part IX, DERIVED scope).
- ``binding`` — scenario-to-chat binding: the versioned
  JSON binding store (``scenario_bindings.json``), the
  materialisation plan, and the bind service that seeds
  a definition's bootstrap lines and initial state into
  an empty chat (P-132, Part IX, DERIVED scope).
- ``binding`` read surface — owner-scoped list / inspect
  summaries over the binding store's list verbs, each
  naming whether its definition still exists (P-135,
  Part IX, DERIVED scope).
- ``organisation`` — scenario library organisation:
  tags, favourites and findability over stored
  definitions in their own versioned JSON document,
  on P-024's tag law (P-134, Part IX, DERIVED scope).
- ``bindpreview`` — binding plan preview: P-132's pure
  materialisation plan for one stored definition,
  handed back read-only in an envelope naming the
  definition's current revision and the bounds of what
  a definition-side plan can promise (P-136, Part IX,
  DERIVED scope).
- ``chatpreview`` — chat-scoped binding plan preview:
  P-136's envelope judged against one named chat —
  bind's refusal facts reported as data and the plan's
  seedable keys split by P-093's own presence law into
  would-seed and already-present (P-138, Part IX,
  DERIVED scope).
- ``deletepreview`` — definition delete-impact
  preview: what deleting one stored definition would
  orphan — its bindings, which do not cascade and
  would read stale, and its organisation row, which
  does not cascade and would stay an orphan — named
  before the irreversible act, in an envelope with
  standing honesty notes (P-139, Part IX, DERIVED
  scope).
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
    list_bindings,
    list_bindings_for_definition,
    plan_materialisation,
    unbind,
)
from runmal.scenarios.organisation import (
    ORGANISATION_FILENAME,
    ORGANISATION_VERSION,
    SORTS,
    TAG_MODES,
    ScenarioOrganisation,
    ScenarioOrganisationError,
    ScenarioOrganisationStore,
    enrich_summary,
    list_tags,
    organisation_path,
    organisation_view,
    query_definitions,
)
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.chatpreview import preview_bind_for_chat
from runmal.scenarios.deletepreview import preview_delete_impact
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
    "ORGANISATION_FILENAME",
    "ORGANISATION_VERSION",
    "SORTS",
    "TAG_MODES",
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
    "ScenarioOrganisation",
    "ScenarioOrganisationError",
    "ScenarioOrganisationStore",
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
    "enrich_summary",
    "list_tags",
    "organisation_path",
    "organisation_view",
    "preview_bind_plan",
    "preview_bind_for_chat",
    "preview_delete_impact",
    "query_definitions",
    "get_binding",
    "list_bindings",
    "list_bindings_for_definition",
    "plan_materialisation",
    "unbind",
    "export_native",
    "export_native_bytes",
    "export_voxta",
    "export_voxta_bytes",
    "parse_scenario_file",
]

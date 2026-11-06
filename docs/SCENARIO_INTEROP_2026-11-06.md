# P-026 — Scenario Content Interop (2026-11-06)

*Part II (Cards & Content Interop): Voxta-shaped scenario files
in/out — what is mappable is mapped to Rúnmál's scenario file
model; unmappable scripting and machinery are reported, never
faked. Acceptance in `tests/test_p026_scenario_interop.py`.*

## The measured gap this slice closes

On entry there was **no scenario unit at all**:

- The delta table (P-004) judges VX-28 (the scenario as a
  unit) **MISSING**: "no scenario unit in the inventory" —
  the scenario/greeting UI edits card fields, not a scenario
  engine, and no scenario object exists anywhere in the tree.
  The rows hanging off it are MISSING with it: VX-29 (core
  settings), VX-30 (template & system-prompt override),
  VX-31 (roles as named slots), VX-32 (bootstrap messages),
  VX-33 (parent scenarios), VX-35–VX-40 (events, actions and
  tools, buttons and controls, contexts), VX-43 (Scriban
  templates), and VX-44 (per-scenario apps).
- What the tree does carry is only a scenario **text field**
  on a character card (`scenario` on the card model, S106):
  one string of situation prose riding inside another unit.
  There is no file shape a scenario of its own can travel
  in, no importer that can read a Voxta-shaped scenario
  file, and no exporter that can hand one back.

This slice builds the file layer only — the road in, the
road out, and an honest report of everything on the file
that Rúnmál cannot yet (or, for scripting, will not ever)
make functional. The scenario storage and engine that
would run a scenario are Part IX work (P-131–P-154); this
slice is exactly the P-018/P-019 precedent: a file model
first, behaviour later.

## What was built

`src/runmal/scenarios/` — a new package, file layer only:

- `filemodels.py` — dataclasses for the whole file as data:
  the scenario file model (the mapped fields in the table
  below), its typed sub-models (role slots, bootstrap
  messages, contexts, impersonation, narrator), the
  complete original mapping in `raw`, unknown top-level
  keys carried verbatim in `extra`, the unmappable elements
  carried verbatim as named data, `ScenarioImportReport`
  (what was mapped, what was carried, and every unmappable
  element with its `path`, `kind`, `name`, and `reason`),
  and the typed `ScenarioParseError` every refusal raises.
- `fileimport.py` — `parse_scenario_file`, the defensive
  importer (see "Defensive import" below).
- `fileexport.py` — `export_voxta` / `export_native` plus
  their bytes variants (`export_voxta_bytes` /
  `export_native_bytes`). Export starts from the original
  `raw` and overlays the normalised mapped fields
  (INV-009); see "Carriage and round-trip".
- `router.py` — a stateless router (see "API" below).

**No database migration and no persistence.** Rúnmál has
no scenario storage or engine yet — Part IX (P-131–P-154)
builds it — so nothing in this slice writes a scenario to
the database, and the schema head stays **0021**. Import
returns the native model plus the honest report; export
takes a model and hands back a file. Neither route stores
anything.

## Mapping — Voxta-shaped JSON to the Rúnmál scenario file model

The importer accepts the Voxta-shaped spellings below.
Where two spellings are listed, the first is the primary
spelling and the second a tolerated alias. Every row cites
the census row (P-003) the behaviour rests on.

| Voxta-shaped key(s) | Rúnmál file-model field | Census |
|---|---|---|
| `name` | `name` | VX-28, VX-29 |
| `description` | `description` | VX-28 |
| `scenario` \| `scenarioText` | `scenario_text` — the situation prose itself | VX-28, VX-29 |
| `chatFlow` \| `flow` | `flow` — `Chat` (normal turn-taking) or `Story` (the user is excluded; the AI narrates and the user watches or triggers) | VX-08, VX-29 |
| `chatStyle` \| `style` | `style` — one of `Companion`, `Roleplay`, `Storytelling`, `Assistant` | VX-08, VX-29 |
| `roles[]` | `roles` — named role slots (sub-fields below) | VX-31 |
| `systemPrompt` | `system_prompt_text` / `system_prompt_mode` (below) | VX-30 |
| `scenarioTemplate` \| `template` | `template_text` — carried verbatim, never evaluated in this slice | VX-30, VX-43 |
| `bootstrapMessages` \| `bootstrap` | `bootstrap_messages` — typed bootstrap messages (below) | VX-32 |
| `impersonation` | `impersonation` — `{name, description}`: who the user plays in this scenario, overriding the user's own identity | VX-05 |
| `narrator` | `narrator` — a string (the narrator's name), or `{name, voice}` | VX-13 |
| `memoryBooks` \| `memory_books` \| `books` | `memory_books` — bound memory books as references (names/ids only; the books themselves do not travel inside a scenario JSON file) | VX-29 |
| `flags` \| `initialFlags` | `initial_flags` — a list of flag names, or an object whose keys are the flag names | VX-34 |
| `variables` \| `initialVariables` | `initial_variables` — an object of initial variable values | VX-34 |
| `contexts[]` | `contexts` — conditional prompt sentences (sub-fields below) | VX-40 |
| `parent` \| `parentScenario` | `parent_ref` — the parent scenario this one inherits from, as a reference | VX-33 |
| `thumbnail` | `thumbnail_ref` — a reference only; image bytes never travel inside a scenario JSON file (see assets, below) | VX-28, VX-60 |

### Sub-mappings

- **Roles** (`roles[]`, VX-31) — roles are named slots,
  referenced by role and never by character name:
  `name` | `role` → the slot's name; `characterName` |
  `character` → the character bound to the slot;
  `enabledOnStart` → whether the role starts enabled (a
  role can start disabled and be enabled later — the
  enabling machinery is Part IX, the datum is mapped
  here); `canSpeak` → whether the role is present but
  silent. A non-object role entry is a typed refusal
  (see "Defensive import").
- **System prompt** (`systemPrompt`, VX-30) — a plain
  string maps to `system_prompt_text` with the default
  mode; the object form `{text, mode}` maps `text` →
  `system_prompt_text` and `mode` → `system_prompt_mode`,
  where `mode` is `replace` or `extend` (the scenario's
  prompt replaces, or extends, the character's own).
- **Bootstrap messages** (`bootstrapMessages` |
  `bootstrap`, VX-32) — two input forms, one model:
  - the list form: a list of `{type, kind, text, role}`
    objects, mapped to typed bootstrap messages keeping
    the declared type/kind, the text, and the role;
  - the string-block form: one string of lines, split
    into one bootstrap message per line. Block-form line
    types are **not declared** in the file and are **not
    inferred** here — each line is carried as an untyped
    line and the report records a warning saying exactly
    that. Guessing a line's type (character, user, event,
    note, secret, instructions) would be faking a mapping
    the file never made.
- **Contexts** (`contexts[]`, VX-40) — each context keeps
  `key`, `text` | `content`, `condition`, `role`, and
  `position` verbatim as data: a short conditional
  sentence, the flag/`$variable` condition it fires
  under, its role filter, and its declared prompt
  position. The condition is carried as data only — nothing in
  this slice evaluates it. Condition evaluation is the
  Part IX scenario engine's work; a condition that cannot
  fire yet is still mapped, never dropped.

## Unmappable machinery

Some Voxta-shaped top-level keys carry machinery Rúnmál
cannot (or, for scripting, will not) make functional.
Detection is **top-level only**, by exact key:

| Key(s) | Report kind |
|---|---|
| `scripts` \| `scripting` | `scripting` |
| `events` | `event` |
| `actions` | `action` |
| `tools` | `tool` |
| `buttons` | `button` |
| `controls` | `control` |
| `hud` \| `hudWidgets` | `hud_widget` |
| `apps` \| `appConfig` | `app_config` |
| `assets` | `asset_bytes` |
| `templateScripts` | `template_evaluation` |

Each is reported in the import report with its `path`,
`kind`, `name`, and `reason`; its original value rides
verbatim in the model's `unmappable_values` and is handed
back unchanged on Voxta export. Unknown top-level keys are
**not** unmappable: they ride in `extra` and are re-emitted
on export like any other carried key.

## Defensive import

- Input is `bytes | str | dict`; byte and text inputs are
  capped at 8 MiB (`MAX_SCENARIO_BYTES`), must decode as
  UTF-8 and parse as a JSON **object**, and must carry a
  non-empty `name` — every violation is a typed
  `ScenarioParseError`.
- Strings are tolerant (a non-string reads as empty);
  structural shapes are strict: a non-list `roles` or
  `contexts`, a non-object role/context/bootstrap entry,
  a non-object `variables`, or a wrongly-typed `flags`
  refuses the file.
- Unknown `flow`, `style`, or system-prompt `mode` values
  never refuse the file: each records a warning and falls
  back (`flow` to `chat`, `style` and `mode` to unset).
- Imported content is data, never code: the scenario
  template and context conditions are carried verbatim
  and are never evaluated in this slice.

## Carriage and round-trip

- `raw` always holds a deep copy of the complete original
  mapping. Voxta export starts from `raw` and overlays the
  normalised mapped fields (INV-009), writing each field
  under the spelling the file itself used where an alias
  exists; the second export of a re-import is a fixed
  point (battery-proven for both formats).
- `export_native` emits clean data only — the mapped
  fields plus `extra`, with `source_format: "native"` as
  the marker — never `raw`, never the report, and never
  the unmappable values. **Carried limitation:**
  unmappable machinery round-trips Voxta → Voxta only;
  a Voxta → native → Voxta pass drops it, and the
  import report is where that loss is named.
- The bootstrap string-block form exports in list form:
  the block's line types were never declared, so there is
  no typed shape to hand back, only the lines themselves.
- Bytes exports are `json.dumps(obj, ensure_ascii=False,
  indent=2)` encoded as UTF-8, with no `sort_keys` — raw
  key order is part of round-trip fidelity.

## API

Stateless, under the same local auth as the rest of
`/api/v1`:

- `POST /scenarios/import` — the request body is the
  scenario file object itself; returns `200` with
  `{source_format, scenario, report}`, where `scenario`
  is the native export of the parsed file and `report`
  is the honest import report. A parse refusal is `422`.
- `POST /scenarios/export?format=voxta|native` — parses
  the body, then returns the exported file object itself
  (`200`); an unknown format or a parse refusal is `422`.

Neither route stores anything.

## Not in this slice

Scenario storage and the scenario engine (Part IX,
P-131–P-154), condition and template evaluation, and the
role-enabling machinery the mapped `enabledOnStart` datum
will feed. This slice is the file layer only.

## Clean-room basis

Own tree only, plus the shapes already logged: P-003's
Voxta census (VX-28–VX-44 and VX-60) from public
documentation. No SillyTavern or Voxta source code was
read; the battery's scenario files are authored inline in
the test module.

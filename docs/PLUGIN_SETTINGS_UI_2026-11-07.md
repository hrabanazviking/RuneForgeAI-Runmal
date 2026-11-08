# P-098 - Plugin settings UI generated from declared schemas (Part VI, Extensions Row)

Roadmap line: *Plugin settings UI generated from declared schemas.*

Clean-room: built from the roadmap line and Runmal's own contracts only - the P-081 settings declaration (stored verbatim; manifest.py names interpretation as P-098's contract), the shipped citizens' actual declarations (scouted in hidden_files/P098_SCOUT.md), the P-089 durable file-store idiom, and the P-094 custody rules. Base 44f6a87 (P-096 banking record). **No migration taken; head stays 0041.**

## What landed

`src/runmal/plugins/settings_ui.py` - a first-class P-081 citizen, id `runmal.plugin-settings-ui`, plus four routes appended to the plugins router:

- capabilities `ui.slots` only; permissions `ui.contribute` only; one settings-panel contribution `plugin-settings-panel` (order 121); its own settings are {schema:{}, defaults:{}} - it honestly has none;
- sandbox grants EMPTY by construction; `register_plugin` only - `build_registry` / `create_app` untouched.

## One renderer, driven by data

`parse_settings_schema(manifest)` interprets the declared {schema, defaults} block into FieldSpecs. Shipped citizens declare flat fields of type string / integer / number with minimum / maximum bounds; the interpreter also honours boolean fields, enum choices, minLength / maxLength, per-field default, title / label, description / help and required, so a future declaration needs no UI code. Widget mapping is deterministic: enum -> select, boolean -> checkbox, integer / number -> number (step 1 / any), string -> text. Labels come from the declaration or are humanised from the field name (max_chars -> "Max chars"); help text is carried verbatim or left empty, never invented.

`build_settings_form(manifest, values)` returns the generated form document {format: runmal-plugin-settings-form, plugin_id, has_settings, status, fields[], values, schema, defaults} where values are the EFFECTIVE values (defaults overlaid with stored owner values). `render_settings_form_html(form)` renders deterministic, escaped HTML - one control per field with min / max / step / checked / selected taken from the form data.

## Honest no-settings surface

A plugin whose schema is empty (six shipped citizens declare {schema:{}, defaults:{}}) or whose manifest carries settings=None gets status `no_settings`, an empty field list and the message "This plugin declares no settings." The HTML renders that sentence and no controls. Writing settings to such a plugin is refused with a named `no_settings` error.

## Validation - strict, named, no coercion

The citizens' own `config_from_manifest` roads are lenient by design (manifest data falls back to constants). The UI write road is the opposite. `validate_complete` refuses with a `SettingsValidationError` whose `errors` list names every bad field with a code: `unknown_field`, `wrong_type` (bools are not integers; an integer field refuses floats and numeric strings; a number field refuses bools, NaN and infinities), `below_minimum`, `above_maximum`, `too_short`, `too_long`, `not_in_enum`, `required`. Nothing is coerced, clamped or silently dropped. Missing fields with declared defaults take the default. `apply_settings_patch` merges a submitted patch over the current effective values and validates the merged document whole, so a patch cannot smuggle an invalid neighbour past validation.

A broken DECLARATION is a different failure class: unknown type, unknown spec key, inverted bounds, a bound on a string field, an empty enum, an invalid declared default, or a defaults entry naming an undeclared field raises `SettingsSchemaError` naming the field - the plugin author's defect, loud at render time, never a half-rendered form.

## Persistence - the declared road, custody-shaped

Owner values live only in this slice's declared store: the P-089 file idiom, one JSON document per owner at `data_dir()/plugin_settings/<user_id>.json`, schema `runmal-p098-plugin-settings-v1`, holding the validated COMPLETE effective values per plugin with an updated_at stamp. Files are written atomically (tmp sibling, chmod 0600, replace); reads re-validate stored values against the CURRENT declared schema - a stored value the schema no longer accepts raises `SettingsStoreError` naming the refusal, never a silent drop, and a corrupt store raises and is never reset. A refused patch writes nothing (battery-proven byte-identical).

Custody (P-094 rules): `export_plugin_settings` returns one checksummed document per plugin (canonical-JSON sha256 over {plugin_id, owner_id, sections}, the packs idiom; an untouched plugin exports an honest `empty` section carrying its defaults). `delete_plugin_settings` removes exactly that plugin's section - its settings leave with the plugin, other plugins and other owners untouched. There is no side-channel store: this file is the one road.

## HTTP surface (plugins router, house idiom)

- `GET /plugins/{plugin_id}/settings-form` - the generated form for the owner.
- `GET /plugins/{plugin_id}/settings` - {values, stored, defaults}.
- `POST /plugins/{plugin_id}/settings` {values: patch} - validates, persists, returns {values, form}; refusal is 422 with the named errors in the detail.
- `POST /plugins/{plugin_id}/settings/delete` {confirm: true} - the custody delete; without confirm it refuses 422.

Manifest resolution: registry record first, else a shipped citizen's manifest through the lazy module map (the P-094 pattern), else 404.

## Scope honesty

Shipped citizens keep reading their manifest defaults at runtime in this slice: their `config_from_manifest` roads are unchanged, so a stored owner value does not yet change a running citizen's behaviour. This slice delivers the generated UI, the strict validation and the durable owner-value store those roads will read; rewiring seven citizens' runtimes mid-row was deliberately not smuggled in. The settings-ui citizen itself is not yet in P-094 custody's fixed citizen list - the same carried-item class P-096 recorded for runmal.game-bridge; its settings sections are exportable and deletable through this module's own custody-shaped verbs above.

## Battery

tests/test_p098_plugin_settings_ui.py - generation from data (a novel synthetic schema with boolean + enum + help text, and a second unseen schema, both through the one renderer; all fourteen shipped citizens render exactly their declared fields, seven with settings and seven honestly empty), named validation refusals for every code, defaults, patch-merge whole-document validation, persistence round-trips (module road and HTTP road), refused-patch byte-identity, owner isolation, export checksum + delete-with-plugin, corrupt and stale stores loud, HTML widget fidelity and escaping, citizen registration, boot registry empty, grants empty, migration head 0041.

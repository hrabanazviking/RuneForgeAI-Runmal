# Variables & State Plugin API (P-093) - 2026-11-07

Roadmap line: "Variables & state plugin API: per-chat
variables/flags (Part IX scenarios consume the same store)."

## What landed

`src/runmal/plugins/variables.py` - a first-class P-081
citizen (`runmal.variables`) carrying ONE shared, durable,
per-chat store of variables and flags. Plugins, the host,
Part IX scenarios and the P-055 macro road all read and
write through the same service functions; there is no
plugin-private silo and no scenario-private store.

- Service API: `set_variable` / `get_variable` /
  `get_entry` / `delete_variable`, `set_flag` / `get_flag`,
  `increment_variable` (addvar semantics), `list_entries`,
  `snapshot_chat`, `clear_chat`, `seed_variables`.
- Provenance on every entry: writer kind (plugin / host /
  scenario / macro) and writer id, created/updated
  timestamps, and a version counter of writes taken. No
  anonymous write path exists.
- Namespacing: a key is `name` or `namespace:name`. A
  plugin's bare keys land in its own namespace; `shared`
  is the documented collaboration surface (a later write
  replaces the value, provenance records who wrote last);
  a plugin addressing another plugin's namespace is
  refused - never a silent overwrite.
- Typing: variables hold JSON scalars only (str <= 4000
  chars, int, finite float, bool, None); flags hold bool
  only; kinds never blur (reading one kind through the
  other refuses; re-kinding an existing key refuses).
  Missing variables raise; missing flags read as False.
  Cap: 500 entries per chat.
- Storage: the P-089 durable file idiom - one JSON
  document per owner at
  `data_dir()/chat_variables/<user_id>.json`, atomic save
  (tmp + chmod 0o600 + replace), corrupt stores raise and
  are never silently reset. NO migration: head stays 0041.
- P-055 bridge: P-055 variables are strings in a
  per-expansion working copy (ephemeral); P-093 entries
  are typed and durable - the difference is deliberate.
  `load_macro_variables` renders the chat's shared
  variables as macro strings; `apply_macro_variables`
  persists an expansion report's map back with macro
  provenance. Plugin-namespaced entries never leak into
  the macro map.
- Part IX contract: a scenario runtime seeds
  `initial_variables` via `seed_variables` (missing keys
  only - seeding never overwrites live state) and then
  uses the same get/set/flag/increment functions with
  scenario provenance.
- Citizen wiring: `register_plugin` only;
  `build_registry` / `create_app` untouched. Manifest
  declares chat.events + ui.slots, chat.read +
  ui.contribute, so the P-082 sandbox grant set is EMPTY.
  The chat.deleted handler abstains: durable state is
  removed only by the explicit clear verb.
- HTTP (plugins router): `GET /chat-variables?chat_id=`,
  `POST /chat-variables/set` (value or flag),
  `POST /chat-variables/unset`, `POST /chat-variables/clear`.
  Chat ownership is verified on every route; HTTP writes
  carry host provenance.

## Evidence

Battery tests/test_p093_variables.py (24 tests);
neighbours P-081 fence + P-055 macros + P-089 + P-090;
counts in hidden_files/P093_EVIDENCE.md.

# P-113 - Plugin Custody Coverage: the F1 Fix (Part VII)

Derived scope, stated plainly: the governing roadmap
gives Part VII only its part line - "VII | Voice, the
Voxta Way | P-101 - P-116" - and no per-slice entries.
P-113 is DERIVED, not roadmap-verbatim, from in-tree
sources only: the P-100 Part VI gate's finding F1
(docs/PART_VI_GATE_2026-11-07.md, carried item K1),
which commissioned - in the gate's own words - to
"extend P-094 CITIZEN_PLUGIN_IDS with
runmal.game-bridge and runmal.plugin-settings-ui at
the next custody touch". This slice is that custody
touch. The keeper reviews this derived scope at
banking.

Clean-room line: built entirely from Rúnmál's own
in-tree contracts - the P-094 custody surface, the
P-096 game-bridge store, and the P-098 settings-ui
module's own custody-shaped verbs - with no outside
source read and no file downloaded (see the P-113
entry appended to docs/CLEAN_ROOM_LOG_2026-10-30.md).

Base: 69ba056 (P-111 banking record). P-112 banks
before this slice in roadmap order and reconciles at
banking; this slice touches no file P-112 touches.
Migration head: 0041. No migration taken.

## 1. The gap, exactly

P-094 custody serves a fixed citizen list. Two
citizens shipped after it - runmal.game-bridge
(P-096) and runmal.plugin-settings-ui (P-098) - were
never added, so a bare-id custody call for either
raised UnknownPluginError: no adapter, no row, no
registration. The gate verified the omission is real,
not cosmetic, and commissioned the fix. The hostage
state is concrete for game-bridge: its durable
per-owner store (seeded dice rolls + declared bridge
events, the P-089 file idiom) could be neither
exported nor deleted through custody at all.

## 2. What was weighed and not taken

- L3, auto-registering the P-091 voice citizens in
  the running app: NOT taken. Registration is
  deliberate host-explicit law (P-081's empty boot
  registry), and each citizen's register_plugin
  already IS the host-explicit road. This slice
  registers nothing; build_registry and create_app
  are untouched, and the battery pins the boot
  registry empty.
- The VX-12 engine half (a TTS backend seam that
  consumes an affect): NOT taken. No backend or
  VoiceInfo carries an affect field on this base;
  it is an engine design across the registry, as
  the P-108 and P-110 scouts already weighed.
- Marking the projected message CONTENT itself
  (the P-105/P-106 leftover): NOT taken. P-106
  declined it on the record under the P-075 law;
  the mark's lawful homes (provenance receipt,
  status views, P-107 rendering) all exist.
- Gallery and conformance in the fixed list: NOT
  taken. F1 names exactly two ids; the gate examined
  the sixteen-citizen corpus and commissioned two.
  Adding uncommissioned ids would outrun its record.

## 3. What landed

All production change is in src/runmal/plugins/
custody.py (+80 lines, additive):

- CITIZEN_PLUGIN_IDS gains "runmal.game-bridge" and
  "runmal.plugin-settings-ui" in roadmap order
  (12 -> 14). Every export document's coverage list
  and custody_coverage() follow automatically.
- _MANIFEST_MODULES gains both module paths, so a
  bare-id export stamps the citizen's real manifest
  instead of None.
- game-bridge joins _FILE_STORES: its store fits
  the idiom exactly (store_path + STORE_SCHEMA), so
  its section ("game_bridge_store", durable_file)
  exports the verbatim store document with counts
  and deletes owner-scoped - one owner's file goes,
  every other owner's file is byte-identical.
- A dedicated section for settings-ui
  ("plugin_settings_store", kind plugin_settings),
  section-scoped through the module's own roads:
  the export carries exactly the settings-ui
  citizen's own section of the shared
  plugin_settings store verbatim (or an honest
  empty - the citizen declares no settings, so
  empty is the expected truth), and the delete
  calls the module's delete_plugin_settings, which
  removes exactly that one section. The shared
  file is never unlinked by custody and no other
  plugin's section is ever exported or removed
  under settings-ui's name. A corrupt store
  reports a loud section error carrying the
  module's own refusal text, on both verbs, and a
  refused delete removes nothing.
- custody_coverage() classifies both honestly:
  game-bridge under durable_file, settings-ui
  under a new plugin_settings classification -
  not durable_file, because no whole-file verb is
  lawful for its shared store.

No HTTP change was needed: the existing custody
roads (/plugins/{id}/custody/export and /delete)
call these same verbs, and the battery pins both
ids serving over HTTP, including the unconfirmed-
delete refusal.

## 4. Labelled updates to pre-existing tests

Two tests pinned the pre-F1 state and are updated
in-slice, at equal or greater assertion strength:

- tests/test_p100_gate.py: the Area C pin
  test_c_custody_fixed_list_omits_two_citizens is
  rewritten as test_c_custody_fixed_list_covers_
  two_citizens (gate battery count unchanged, 16):
  both ids present, 14 ids, coverage matching, and
  bare-id exports that stamp manifests, carry the
  data sections and verify checksums. The gate
  record document itself is unchanged history.
- tests/test_p094_plugin_custody.py:
  test_coverage_names_every_citizen's expected
  durable_file set gains "runmal.game-bridge".
  No other assertion in the file changes.

## 5. Honest limitations carried

- Stored settings FOR a citizen (any plugin's
  section in the plugin_settings store) are still
  not part of that citizen's own custody export
  or delete - unchanged from P-094 for every
  citizen. Only settings-ui's own section is
  custody data in this slice. Named, not silently
  half-wired.
- game-bridge's in-memory observation list
  (handler metadata, lost on restart by design)
  is not custody data; its durable store is.
- runmal.gallery and runmal.plugin-conformance
  remain outside the fixed list (section 2).
- L3 stands exactly as banked: the P-091 citizens
  remain unregistered in the running app, by
  deliberate host-explicit design.

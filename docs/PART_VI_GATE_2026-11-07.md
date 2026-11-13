# P-100 - Part VI Gate (2026-11-07)

*The Part VI gate. The roadmap's own text for this slice is:
"P-100 Part VI gate: the row ships with P-084-P-090 + P-095 live;
a third-party-shaped test plugin (written blind against the docs)
installs and runs." Part VI's goal, in the roadmap's own words,
is: "the mirrors grow by extensions; Runmal grows by a plugin row
of its own -- a real API, a real sandbox, and the beloved
extensions rebuilt as citizens". This record is that gate, judged
only from Part VI's banked records, the battery module, and the
tester's logs filed with this slice; no mirror source consulted
(clean-room).*

## Gate verdict

**Part VI is COMPLETE and the gate PASSES with named carried
items and one finding.** This record claims only what the battery
proves.

Verdict per area: Row PASS, Blind PASS, Accounting PASS.

## S1 The gate checklist

| Gate requirement (roadmap text) | Evidence | State |
|---|---|---|
| The row ships with P-084-P-090 + P-095 live | conformance kit as shipped, battery A | DONE HERE |
| The full shipped corpus passes the kit | sixteen citizens, battery A | DONE HERE |
| The citizens compose without interfering | one registry through the P-081 API, battery A | DONE HERE |
| A third-party-shaped test plugin installs | P-083 local pack + manager road, battery B | DONE HERE |
| The blind plugin runs | real chat flow, settings, custody, battery B | DONE HERE |
| Honest accounting of carried items | battery C pins each one | DONE HERE |
| Measured counts at the gate | S6 of this record, from the tester's logs | DONE HERE |

Part VI spans P-081..P-100, twenty slices continuous:
P-081 through P-100, no gaps. Per-slice coverage map:
P-081->A/B/C (the API the whole gate speaks),
P-082->A/B (the sandbox grants every citizen re-proves),
P-083->B (the manager road), P-084->A, P-085->A, P-086->A,
P-087->A, P-088->A, P-089->A, P-090->A,
P-091->A (neighbours at the gate; no gate area claims it alone),
P-092->A (neighbours), P-093->A (neighbours),
P-094->B/C (the custody road and its fixed list),
P-095->A, P-096->A/C (a corpus citizen; named in finding F1),
P-097->A/B (the kit itself), P-098->B/C (the settings UI),
P-099->B/C (the failure manners), P-100->this gate.
No roadmap text was edited.

## S2 "Passes" means, per verdict area

- **Row PASS.** Every roadmap-named citizen (runmal.summarise,
  runmal.vector-storage, runmal.translate,
  runmal.image-generation, runmal.web-search,
  runmal.quick-replies, runmal.regex-scripts, runmal.gallery)
  passes the P-097 conformance kit as shipped and is listable;
  the full shipped corpus of sixteen citizens passes with no
  failures, its listable set is exactly its passing set, and
  the corpus document is deterministic (an equal checksummed
  core, twice). All sixteen citizens register and enable in
  ONE registry through the P-081 API: sixteen UI contributions
  stand active, a chat.created dispatch is delivered to the ten
  subscribed citizens with no failures and no strikes, the
  slots prompt stage runs its four citizen hooks and the
  messages stage its two, every hook abstaining cleanly on a
  stateless seed, and the seed slot and seed message pass
  through both stages byte-intact.
- **Blind PASS.** The blind plugin (S3) passes the conformance
  kit on data alone, its submission unmutated by the checking;
  packaged as a P-083 local pack it previews installable,
  installs and enables through the manager road, stands as an
  enabled subscriber to its declared events with its sidebar
  contribution active and its ledger row written by the
  manager; its settings schema renders through the P-098 UI
  (a text field and a number field), a valid patch stores and
  reads back merged, and refused patches (below the declared
  minimum, a wrong type) store nothing; its data exports
  through the P-094 custody road as one checksummed document
  (host ledger and registration sections, both exported) and
  deletes through the same road, finishing through the
  manager uninstall, after which a fresh export refuses it as
  unknown; bound through the documented citizen registration
  road, its declared events fire in a real HTTP chat flow --
  chat.created, then message.created carrying the message text
  under its declared chat.read permission, while a sibling
  without chat.read fires with the text redacted to a character
  count; and when its handler is made to crash, three real
  message posts still answer 201, the plugin disables itself
  at the failure limit with a plain report that carries no
  secret, the chat and the sibling carry on unaffected, and
  the errored plugin is never invoked again. A manager
  uninstall leaves the registry, the ledger and the UI
  contributions empty, and no shipped source file names the
  blind plugin: it lives only in the gate battery.
- **Accounting PASS.** Every carried item named in S4 is
  pinned by a battery measurement at this gate, at full
  strength: the custody list omission is proven both ways
  (bare-id export refuses both omitted citizens; registered
  export serves both), the settings store's distance from a
  running citizen is proven on a live translate citizen, the
  process-local failure state is proven against a fresh
  registry, and the empty boot registry is proven on the
  gate's own tree. Nothing was loosened to make an area pass.

## S3 The blind plugin

The battery's third-party-shaped plugin is a word counter
(id acme.word-counter, battery world ZqxGate100),
fresh-authored for this gate against the documented plugin
surface only: docs/PLUGIN_API_V1_2026-11-07.md,
docs/PLUGIN_MANAGER_2026-11-07.md,
docs/PLUGIN_SETTINGS_UI_2026-11-07.md,
docs/PLUGIN_DATA_CUSTODY_2026-11-07.md and
docs/PLUGIN_CONFORMANCE_KIT_2026-11-07.md. It declares the
chat.events and ui.slots capabilities, the chat.read and
ui.contribute permissions, the chat.created and
message.created events, one chat.sidebar contribution, and a
two-field settings schema (a string greeting, a bounded
integer max_words). It declares no prompt hooks, because the
documented pack road carries data only (carried item K5):
the pack installs its manifest, and its executable handlers
bind through the documented citizen registration road, which
is the road battery B exercises for the chat-flow and crash
proofs. No SillyTavern or Voxta source was consulted for it,
and it reads no real user files.

## S4 Carried items - named and deliberate

The gate passes with these items carried, not hidden. Each
is exact in the battery module or the banked slices' own
records; this section names them so no later part mistakes
them for clean ground.

- **K1 - The P-094 fixed citizen list omits two citizens.**
  CITIZEN_PLUGIN_IDS names twelve ids; runmal.game-bridge
  (P-096) and runmal.plugin-settings-ui (P-098) are not in
  it, so a bare-id custody export for either refuses as
  unknown. Both citizens are custody-reachable once
  registered or pack-managed (the battery proves the
  registered road for both). See finding F1.
- **K2 - P-098 stored values do not yet change a running
  citizen's behaviour.** Citizens derive their runtime
  config from their manifest at registration (the translate
  citizen's config is the measured example); the settings
  store is read by the settings form and router roads, not
  by any running citizen. Saving stored values is real and
  durable; wiring them into live behaviour is a future
  slice's work, not a claim this gate makes.
- **K3 - P-099 failure state is process-local.** Strikes,
  failure history and the ERRORED state live in the
  in-memory registry (the P-081 design: nothing persists
  across a restart in v1). The manager ledger persists
  installs and enable decisions, not failures; a restarted
  host starts every plugin with a clean failure record.
- **K4 - The P-081 empty boot registry is deliberate.**
  build_registry starts with zero in-tree plugins; citizens
  join only through trusted register_plugin calls, and
  pack-installed plugins return through manager rehydration.
  The gate re-proves the empty boot on its own tree.
- **K5 - The pack road is data-only in v1.** No code travels
  in a manifest, a pack, or an HTTP request; a pack-installed
  plugin's handlers are empty by design, so its live
  surfaces are its subscription, its UI contributions and
  its settings schema. Executable behaviour binds only
  through trusted in-tree registration (the citizen
  pattern). This is the documented security posture, and
  area B is judged inside it, not around it.
- **K6 - Custody deletion spans two surfaces for a pack
  plugin.** The P-094 delete removes the ledger row and the
  registration (finishing through manager.uninstall); the
  plugin's P-098 settings section is removed by the settings
  store's own custody delete. The battery exercises both,
  after which no blind-plugin data remains anywhere.

## S5 Findings for the keeper

- **F1 - The P-094 fixed citizen list omits runmal.game-bridge
  (P-096) and runmal.plugin-settings-ui (P-098); extend it at
  the next custody touch.** Both citizens banked after the
  list was fixed. The omission is narrow (registered and
  pack-managed custody both reach them, proven in battery C)
  but real: a bare-id export or delete for either refuses as
  unknown. The commissioned follow-up is one slice: add both
  ids to CITIZEN_PLUGIN_IDS and custody_coverage, with the
  P-094 battery re-pinned to the fourteen-id list at equal
  strength. It is NOT made in this slice, whose commit is
  gate files only and must not collide with the P-094
  banking records.
- **F2 - No new engine defect was found by this gate.** Every
  Part VI surface produced exactly its promised result in
  the battery: the kit, the corpus, the composed registry,
  the pack road, the settings road, the custody road, the
  real chat flow and the failure manners. The gate's only
  corrections during construction were its own probe and
  assertion errors, recorded in the slice evidence. Nothing
  was left unfixed in this slice's own files. The P-064
  findings F1/F2 are not touched by this gate and are not
  restated here.

## S6 Evidence at the gate

Measured counts, from the tester's logs filed with this
slice (hidden_files/p100_battery.log,
hidden_files/p100_neighbours.log and
hidden_files/p100_fullsuite.log):

- Gate battery: 16 passed - the one P-100 behaviour module: tests/test_p100_gate.py (16 tests). 4 + 7 + 5 = 16 behaviour tests (Area A 4, Area B 7, Area C 5).
- Gate-record module: tests/test_p100_gate_record.py (10 tests) - R = 10.
- Neighbours batch as run by the tester: 628 passed - the Part VI plugin fence, tests/test_p081_plugin_api.py through tests/test_p099_failure_manners.py (nineteen modules), 0 failed.
- Full suite: 4067 passed, 4 skipped, 0 failed (the run listed below, taken with both gate modules in the tree). The earlier run, taken before the gate-record module landed, read 4057 passed, 4 skipped, 0 failed -- exactly the baseline plus the battery.
- Baseline: the P-099 banked tree measured B = 4041 passed, 4 skipped at its own banking. 4041 + 16 + 10 = 4067, so full suite == B + 16 + R, exact.

Migration note: none. This gate adds no migration; the
migration head remains 0041 and no migration was added by
this slice. This slice is committed on yrsa/runmal-team-03
for the keeper to bank in roadmap order.

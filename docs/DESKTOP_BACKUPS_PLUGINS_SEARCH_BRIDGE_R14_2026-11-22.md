# R-14 — Backups, Plugins, Library Search, Bridge (desktop definition)

Date: 2026-11-22. Slice R-14 of the Interface Redo plan
(Part 3): "Backups, Plugins, Library Search, Bridge.
§2.3.13/14/15/17 surfaces. *Verification:* launch proof —
make a backup from the window, stage-restore it; toggle a
plugin; run one library search."

## Ground truth (engine, read from source 2026-11-22)

- **Backups** (`src/runmal/backups/`): `POST /backups`
  (database backup, 201), `GET /backups`, `POST
  /backups/{filename}/stage`, `POST /backups/full` (full
  bundle, 201), `POST /backups/full/{filename}/stage`,
  `POST /archive/import`. Two truths the window must speak:
  **the listing is database backups only** (its filename law
  matches `runmal-backup-*.db`) — full bundles never appear
  in it and are staged by the name their creation returned;
  and **staging is not restoring** — a staged restore waits
  in the restore area for review and never overwrites the
  live data.
- **Plugins** (`src/runmal/plugins/`): manager + registry
  (`GET /plugins/manager`, `GET /plugins`), install
  (`POST /plugins/install/preview`, `POST
  /plugins/install` — the body is the local pack envelope
  under `pack` plus `granted_permissions`), detail,
  permission card, failure reports, and the lifecycle verbs
  (update — which requires the new pack in the body —
  uninstall, enable, disable, acknowledge), plus the two
  citizen stores on the same router: quick replies (CRUD +
  execute + executions) and expression sets (CRUD +
  bindings + derive + current), and the per-chat variables
  store (P-093). **A fresh engine registers zero plugins** —
  the manager answers `{"installed": [],
  "rehydration_problems": []}` and the registry list is
  empty; there is nothing to toggle until a pack is
  installed. And **"disabled" is a runtime state, not a
  persisted one**: the durable truth is the ledger's
  `enabled` flag, and rehydration returns a not-enabled
  plugin as `registered`. The window renders the state the
  engine reports, in each moment, without inventing a
  persistence the engine does not have.
- **Library Search**: exactly two search roads exist —
  `GET /hub/unified-search` (owner-wide, over hub entry
  metadata + verified pack contents) and the workspaces
  unified search, which is **chat-scoped by engine law**
  (it needs a `chat_id` and a bound folder). **Faces has no
  search route at all** (presentation/roster/census
  routers only). The fan-out therefore returns `hub`
  always and `workspaces` only when a chat is named; a
  `faces` key is never fabricated.
- **Bridge** (`src/runmal/bridge/` admin router): `POST
  /bridge/credentials` (201; body `name` + `scopes`, scope
  grammar `<capability>:<resource>` with `*` wildcards),
  `GET /bridge/credentials`, `POST
  /bridge/credentials/{id}/revoke`. The creation response
  is the one place the token plaintext ever appears
  (INV-023): list payloads, views, and every words function
  are built token-free by construction.

## The slice

- Client: backups list/create/create-full/stage/
  stage-full/import-archive; plugins manager/list/detail/
  permission-card/failure-reports(+single)/install-preview/
  install/update/uninstall/enable/disable/acknowledge;
  quick replies list/create/get/update/delete/execute/
  executions; expression sets list/get/create/update/
  delete/bindings/derive/current; chat variables
  get/set/unset/clear; library search (`search_hub`,
  `search_workspaces`, the `search_library` fan-out);
  bridge credentials list/create/revoke. Models
  `BackupView` (both engine shapes; `kind` from the
  filename law), `PluginView`, `PluginFailureReportView`,
  `QuickReplyView`, `ExpressionSetView`,
  `BridgeCredentialView` (id/name/scopes/state only —
  `label`/`state` are derived properties; a `token` key in
  a payload is ignored by construction), `LibraryHitView`.
  No new engine routes.
- Qt-free flows: `desktop/backups_logic.py`,
  `desktop/plugin_logic.py`, `desktop/library_search_logic.py`,
  `desktop/bridge_logic.py`. Two translations live in the
  flows, where they belong: the plugin flow resolves the
  window's install payload (a pack-file path) into the
  engine's body, granting exactly the permissions the
  envelope's own manifest declares (preview sends `pack`
  alone, as its road reads); the bridge flow translates
  the form's `label` to the engine's `name`.

## What was built

Four dialogs, all over existing engine routes (census
unchanged at 365 paths / 455 operations), in the Tools
menu in plan order after Vision:

- **Backups & Data** (Tools ▸ Backups & Data…): the
  backup list in words, Create Backup / Create Full
  Backup, Stage Restore / Stage Full Restore behind
  custody-naming confirms whose text states that staging
  prepares a restore for review and does NOT overwrite
  the live data, and Import Archive…. Because full
  bundles never appear in the engine's listing, full
  backups created in the visit are remembered by the
  dialog and listed from that memory (their creation name
  is their staging key); the stage buttons refuse the
  wrong kind of row in plain words rather than sending a
  database name down the bundle road or vice versa.
- **Plugins** (Tools ▸ Plugins…): four tabs. *Manager* —
  the manager summary, the plugin list, a detail pane
  joining the detail words and the permission card,
  Enable/Disable/Update/Acknowledge on the selection
  (Update takes the new pack from the install field, and
  without one the refusal says why), Uninstall behind a
  no-undo confirm, and Install: a source field naming a
  pack file, Preview rendering the engine's verdict, then
  Install. *Quick Replies* — the list, a name+text create
  form, Execute and Delete. *Expressions* — the sets list,
  per-set detail, and the current-expression words.
  *Failures* — the failure reports in words.
- **Library Search** (Tools ▸ Library Search…): one
  query box; results grouped by source with the fan-out's
  summary words — on an estate with no hub entries the
  honest answer is an empty hub, said plainly.
- **Bridge** (Tools ▸ Bridge…): the credential list and
  status words (counts by state, scopes in force), Create
  Credential (label + comma-separated scopes), the token
  shown exactly once in a dedicated one-time field with
  words saying it is not stored by the window — never in
  the status label or summary — and Revoke behind a
  confirm.

**Integration findings (coordinator, fixed in-slice):**
(1) The window crew's fake views carried contract fields
the real renderers do not read; the window tests now build
the client layer's real view classes, exactly what the
dialogs receive in production. (2) The install payload
the dialog composes (a pack-file path) is not the engine's
body — the flow now resolves it (above); the fake
transport could not have caught this, the live proof did
its job by design. (3) The bridge form's `label` is not
the engine's `name` — translated in the flow. (4) The
full-backup listing truth (above) — dialog session memory
+ kind guards.

**Gates (VM seat, swift standard):** slice logic 16/16 +
live 6/6; neighbour batch (R-13 logic+live, R-04 client,
P-207 census, P-232 file) inside a 95-test run with only
the known pre-existing P-232 H1 failure; window tests
R-14 11/11 with R-13 + R-12 neighbours = 27/27 under real
PySide6 offscreen; full-suite collection 6,711 (was
6,689); ruff clean. Launch proof
`scripts/desktop_r14_proof.py`: **35/35 PASS** on the VM
(Linux x86-64, Qt 6.8.0 / PySide6 6.8.0.2, offscreen) —
backup created in the window and its restore staged with
the not-overwritten words kept, full backup staged by its
creation name, the fresh manager honestly empty, a real
pack minted with the engine's own builder previewed +
installed through the dialog, its permission card
rendered (chat.read), the plugin toggled enabled →
disabled with states verified through the client
(`registered → enabled → disabled`), a hub entry found
from the window's search box, a bridge credential created
with its token in the one-time field only and revoked
through the dialog, and a restart proving the backup, the
plugin (back as `registered` — the engine's durable
not-enabled truth), the revoked credential, and the hub
entry all persist; clean quit stops the engine.

**Venue record:** as R-13 — the proof ran on the VM;
purplelongship and Mimir launch proofs are deferred
(fleet unreachable from the coordinator's sandbox:
no SSH server on purplelongship, Mimir refused the VM's
key), purpleraider deferred under Volmarr's pause, and
the F15 (Windows) proof rides with the owed proofs at
R-17.

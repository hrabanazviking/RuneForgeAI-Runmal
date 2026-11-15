# Desktop shell R-09 — Connections & Generation settings (2026-11-15)

Slice R-09 of `RUNMAL_INTERFACE_REDO_PLAN_2026-11-14.md` (Part 3):
the backend-profiles page over the R-02 routes (key entry, health,
model picker, per-chat pin) + presets & sampler panel (the full
29-field set, bundles/packs/overrides/resolve preview). Plan
verification: *switch the active profile in the window and watch
the next reply come from the other backend; change temperature in
a preset and see it in the resolve preview.*

## Definition (before implementation)

- **Owning subsystem:** the desktop shell (`src/runmal/desktop/`)
  over the existing engine roads — R-02 backend-profiles
  (`backends/router.py`), S207 presets + P-054 bundles/overrides/
  packs + `GET /presets/resolve` (`presets/router.py`), and the
  chats pin/preset roads. **No new engine routes** (census
  discipline stands at 365 paths / 455 operations).
- **Inputs:** profile rows (R-02 shape; secrets only as
  `has_*_secret` booleans), preset rows (`preset_to_dict`: name,
  params bag, template_ref, source_format, prompts carriage),
  bundle documents (P-054 validated shape), override rows,
  pack payloads, and the resolve view (effective bundle + per-field
  sources + applied/shadowed rows).
- **Outputs:** two Tools-menu dialogs — Connections (profiles) and
  Generation (presets / bundles & overrides / resolve preview) —
  plus a Session-dock preset quick-apply control.
- **Invariants:** INV-023 (API keys are write-only: they travel
  once, in the secret-route request body, and are never displayed,
  logged, retained by the client, or echoed — the form shows only
  the stored/not-stored state); the preset bag is *open* — unknown
  keys are preserved verbatim through every edit (the shell splits
  known/extra and carries extras untouched, exactly as the engine
  does); sampler ranges in the form mirror
  `backends/params.py` (the values that can actually take effect
  at generation), while saving is validated by the engine's
  `presets.validate_params` and its words are surfaced verbatim.
- **Failure behaviour:** every engine refusal (422/409/404) is
  shown as words in the dialog, never a frozen window or a silent
  drop; all network work runs off the GUI thread (workers, as
  R-04…R-08); health is rendered in plain words (the R-05
  `health_words` pattern), never raw JSON.
- **Study lessons applied** (goal studies folder): Voxta #3 —
  one uniform settings form per provider with an embedded
  "test this connection" verb (here: the health probe + model
  fetch on the profile form itself); Voxta #4 — the probe returns
  a structured verdict rendered as words; SillyTavern "not to
  take" — no flat settings ocean and no jargon-first naming:
  sampler fields are grouped by user task and every control is
  labelled with a human name first, the technical key second.
- **Compatibility:** `PresetSummary` (R-06 session display) is
  untouched; the full preset shape lands as a new `PresetDetail`
  model. The engine has **no default-profile concept** —
  generation resolves explicit profile → chat pin → engine
  default (R-03) — so the page's switching surface is the
  per-chat pin, named honestly; no default is invented.

## Acceptance contract

1. Logic tests (Qt-free, MockTransport): the sampler catalogue is
   exactly the engine's canonical 29 bag keys; bag split/merge is
   lossless for unknown keys; local validation words mirror the
   engine's ranges; the settings flow round-trips profiles
   (create/update/secret set+clear/pin), presets (CRUD, duplicate,
   apply, import/export), bundles (CRUD, share, import), overrides
   (set/list/delete) and resolve — with a canary key proving no
   secret value ever appears in a response the flow handles.
2. Live tests (real in-process engine): the same roads end-to-end
   on a fresh data dir, incl. a composed turn whose recorded
   backend request carries the applied preset's temperature.
3. Window tests (Qt): both dialogs construct and drive over a
   fake flow; the sampler form round-trips a bag (set → read back
   identical, extras preserved); the Session-dock quick-apply
   calls the flow's apply road.
4. Launch proof (`scripts/desktop_r09_proof.py`): in the real
   window — create two profiles (Demo + a local echo backend),
   pin one to a chat and send (reply from that backend), pin the
   other and send (reply from the other backend, Session dock
   agrees); create a preset with temperature 0.9, apply it, and
   see 0.9 in the resolve preview; create a bundle, assign it to
   the chat as an override, and see it in the resolve preview;
   restart the app — profiles and preset persist; clean quit
   stops the engine.
5. Neighbour gates: R-02…R-08 batches + S207/P-021/P-054 preset
   engine tests + P-207 census + S806/S807 stay green; the P-232
   file shows only the known pre-existing H1 footprint failure;
   full-suite collection count tracked; ruff clean on new files.

## What was built

- `src/runmal/desktop/settings_logic.py` (new, Qt-free): the
  29-field sampler catalogue (`SAMPLER_FIELDS`, verified set-equal
  to `presets/service._CANONICAL`), grouped for the form; open-bag
  `split_bag`/`merge_bag`; `validate_bag` with label-worded
  problems; stop-sequence and logit-bias text codecs (bias token
  ids sorted numerically); human backend labels; `SettingsFlow`
  over the client (profiles + write-only secret tri-state,
  probe → plain-words health + model list, per-chat pin,
  presets, bundles composed over the stored document, overrides,
  packs, resolve) and the resolve helpers `carried_sections`,
  `effective_rows`, `resolve_notes`.
- Client roads (`client/core.py`, models `PresetDetail`,
  `BundleView`, `OverrideView`): profile secrets (chat set
  existed; chat clear + embedding set/clear added), preset
  detail/create/update (PATCH)/delete/import/export, bundle
  list/get/create/update (PATCH)/delete/share/import, override
  list/set/delete, pack inspect/import/export, and
  `resolve_presets` returning the P-054 effective view. Census
  unchanged: 365 paths / 455 operations; no new engine routes.
- `window.py`: `SamplerFormWidget` (one generated form for
  presets, bundles, and override deltas), `ConnectionsDialog`,
  `GenerationDialog` (Presets / Bundles & Overrides / Resolve
  Preview tabs), real Tools ▸ Connections… / Generation…
  actions replacing the R-09 placeholders, Session-dock buttons
  and a preset quick-apply combo; any settings change refreshes
  the shell and reopens the open chat so the dock tells the
  truth.
- Tests: `tests/test_r09_settings_logic.py` (13),
  `tests/test_r09_settings_live.py` (3, incl. the composed turn
  carrying the applied preset's temperature to a recording
  backend on the real engine, and the INV-023 canary),
  `tests/test_r09_desktop_window.py` (3). R-04's structure test
  now asserts the graduated real Tools actions (the same
  superseded-placeholder pattern as R-05/R-06 before it).
- Proof: `scripts/desktop_r09_proof.py` — 33 checks driving the
  real app: Demo profile pinned → Demo reply; profile "Echo B"
  created through the dialog against a local echo server, pinned
  → echo reply; preset temperature 0.9 set in the sampler form,
  applied, shown in the resolve preview, and observed on the
  wire; bundle + chat override delta resolved with sources;
  restart persistence; clean quit stops the engine.

### Gate evidence (2026-11-15, seat purplelongship)

- Logic 13/13, live 3/3 (venv312 + PYTHONPATH), window 3/3
  (shell venv, PySide6-Essentials 6.8.0.2, offscreen).
- Neighbours: R-02…R-08 logic/live + S207 + P-021 + P-054 +
  P-207 + S806 + S807 = 216 passed; window neighbours
  (R-04…R-09) green; the P-232 file shows only the known
  pre-existing H1 footprint failure. Full suite collects 6,637
  (R-08: 6,621; +16 Qt-free tests). Ruff clean on all new and
  touched files.
- Launch proof 33/33 PASS: purplelongship (Linux x86-64,
  offscreen) and Mimir (Linux ARM aarch64, offscreen). Evidence:
  goal `hidden_files/r09-evidence/`.
- **Deferred venues:** purpleraider (offscreen + workshop
  Wayland) — deferred under Volmarr's purpleraider pause, as
  recorded in the campaign state. F15 Windows (offscreen) —
  deferred: the machine was unreachable on 2026-11-15 (no route
  to its recorded LAN address, ARP FAILED, no SSH listener on
  any live subnet host — powered off or asleep); to be run when
  the F15 is next awake, and in any case at R-17.
- Bugs found and fixed in-slice: dialog reads of `base_url`
  from the profile `config` (not a model field); a second Save
  creating a duplicate profile (the dialog now tracks the saved
  id); generation-counter guards + quiet refresh fallbacks so a
  pending load cannot refill a form or clobber the status line
  after a user action; `template_ref=None` normalisation in the
  flow; httpx `json=` payloads in the fake transports.
- Transport note: the slice was authored on the VM clone and
  carried to the seat over a git transfer branch
  (`yrsa/r09-transfer`, deleted at banking) after the
  base64/file.write road corrupted a 631-byte file and the
  VM→laptop HTTP proxy road reset; main moved only at banking,
  from the seat, after gates — the same discipline as the
  tarball road.

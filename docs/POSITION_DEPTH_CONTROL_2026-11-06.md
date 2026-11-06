# Position & depth control (P-038) — 2026-11-06

Roadmap line: *P-038 Position & depth control: entries inject
at declared positions/depths in the prompt (the composer
contract honoured).*

Part III (Lorebook Depth), from
`docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`.

## The dishonesty this removes

Placement was declared everywhere and honoured almost nowhere:

- The file layer had known `at_depth` since P-019 (position
  code 4 mapped as data), but the DB layer rejected it:
  `service.VALID_POSITIONS` held only `before_char` /
  `after_char`, so a native lorebook carrying an `at_depth`
  entry could not enter the DB store at all
  (`import_book_transactional` raised `ValueError`) — gate
  finding **F1** — and the DB-path importer collapsed code 4
  to `before_char`, losing the declared placement silently
  (P-030 pinned loss (a), position half).
- The at-depth companions `depth` / `role` survived only as
  file-layer data. No storage, no service field, no engine
  read them; the role code table was explicitly left
  undefined ("Part III's to define", P-019).
- The one production-shaped composition path, the prompt
  inspector, built **every** included lore entry as a
  `lore_before` slot with role `system`, whatever position
  the entry declared. The composer's depth-injection contract
  (S206) existed but no lore entry could reach it.

## What was built

- The placement module — new `src/runmal/lorebooks/placement.py`,
  pure (no DB, no I/O): the single vocabulary owner both layers
  import, so the file/DB split F1 recorded cannot recur.
  - Positions: `before_char`, `after_char`, `at_depth`;
    world-info codes {0, 1, 4} and their inverse.
  - The role code table, defined by this slice as Rúnmál's
    own: {0: `system`, 1: `user`, 2: `assistant`} — Rúnmál's
    `VALID_ROLES` vocabulary in baseline order; names map back
    to codes on world-info export.
  - Strict checkers (`check_position` / `check_depth` /
    `check_role`) for the service/API write path: depth is
    `None` or a real `int >= 0` (bools, floats, strings,
    negatives rejected); role is an exact name (codes are a
    file-format concern, never API input).
  - Tolerant normalisers for the file legs, degrading
    asymmetrically on purpose: a bad depth becomes `None`
    (undeclared — never an invented number, never clamped:
    clamping a negative depth to 0 would invent the most
    intrusive placement), while a bad role becomes `system`
    (role has no absence sentinel — the column is NOT NULL
    and the composer needs a concrete role). Bools never
    coerce (`True` is not depth 1, not role code 1).
  - `placement_for(position, depth, role)` → the frozen
    `Placement(kind, depth, role)`: before → (`lore_before`,
    None, system); after → (`lore_after`, None, system);
    at_depth → (`lore_before`, effective depth, stored role).
    The effective depth materialises `DEFAULT_AT_DEPTH_DEPTH`
    (4) only here, at placement time, when the stored depth
    is undeclared or unusable; storage and files keep
    undeclared as undeclared. Before/after placements force
    role `system` and depth None, so companions stored on
    such entries can never leak into a slot.
- Storage: migration 0030 (**PROVISIONAL** — 0029 is reserved
  for P-037, scan depth & context windows, building
  concurrently from the same base and banking first; the
  keeper renumbers at banking if the reservation changes)
  adds `lore_entries.depth INTEGER` (nullable) and
  `lore_entries.role TEXT NOT NULL DEFAULT 'system'`. The ORM
  gains both fields. Existing rows read back depth NULL /
  role 'system' — exactly their old behaviour (no at_depth
  entry could be stored before this slice).
- Service + API: `VALID_POSITIONS` is placement's (re-exported
  from service for existing callers; `service._check_position`
  remains as an alias of the strict checker); `create_entry` /
  `update_entry` carry `depth` / `role` under strict
  validation (update can clear depth back to None);
  `entry_to_dict` exposes both (stored values verbatim — the
  effective default is never materialised there). The entry
  create/update API shapes gain `depth` (nullable, `ge=0`)
  and `role` (name; update nullable).
- Import/export: `depth` / `role` are modelled on both file
  legs, so they leave the pinned dropped-field sets (see Test
  maintenance).
  - `transfer.py`: world-info entries map position code 4 to
    `at_depth` (the F1 collapse is deleted), `depth` through
    the tolerant normaliser, and the role code to the stored
    name; native entries carry `depth` + `role` (a native role
    arriving as a code is tolerated); `export_book` emits both
    for every entry (the transfer layer's unconditional
    pattern); `validate_parsed_book` prepares them for the
    transactional import (depth strict, role normalised then
    checked), so both import paths store at_depth books whole.
    The Gale-Bell entry: position 4 / depth 4 / role 0 in →
    `at_depth` / 4 / `system` stored.
  - `interop.py`: `WorldInfoEntry.role` is now the normalised
    NAME (it was the verbatim code object before this slice);
    the position code tables are placement's, re-exported
    under their historical names; `native_fields()` carries
    depth/role; world-info export writes the role back as its
    code under the no-fabrication rule (only when the source
    file carried a role or the role differs from `system`)
    and depth only when declared — the native fixture's Ferry
    (at_depth, neither declared) exports to world-info with
    position code 4 and **neither** companion key.
- Preview (`preview.py`, additive): every row gains `position`
  (the declared position, normalised), `role` and
  `injection_depth` — the EFFECTIVE placement from
  `placement_for` (preview answers "what will the prompt do";
  `entry_to_dict` answers "what is saved" — the two are not
  conflated). `injection_depth` is deliberately not named
  `depth`: the row's existing `depth` key is the P-031
  recursion depth, and the collision is pinned by the battery.
- Inspector (`prompt/inspect.py`): included lore rows become
  slots through `_lore_slot`, which honours the row's
  placement — before → `lore_before`, after → `lore_after`,
  at_depth → a `lore_before` slot carrying `Slot.depth` (the
  S206 splice count) and the entry's role; discarded rows
  report the same kind/role in the trace. The composer itself
  is unchanged: S206 already implements the contract.
  - **Defect found and fixed in-slice:** the naive wiring — a
    `lore_before` slot (baseline order 3) carrying a depth —
    would never splice: the composer reaches order-3 slots
    before the history slot (order 6) exists, finds no history
    to splice into, and falls through to plain emission, the
    depth silently unhonoured. At-depth lore slots therefore
    keep kind `lore_before` (trace grouping unchanged) but
    take the baseline order of the depth-injection position
    (`authors_note`, order 8) as explicit slot data — ordering
    stays data, never a hidden branch (PROMPT_COMPOSER.md
    §2). With no history they emit at that order position —
    after plain lore, before post-history instructions. The
    battery pins both the order and the end-to-end splice
    through `_lore_slot` itself.
- Archive: no code change — the .runmal archive serialises
  lore entries by table columns, so depth/role ride along;
  the neighbours (s801/s802) pin export/restore at head 0030.

## What was deliberately NOT wired

- No new slot kind for at_depth: kind encodes source family,
  depth is an attribute of the slot (the composer's own
  precedent — a depth-carrying Author's Note stays kind
  `authors_note`). `LORE_KINDS` and the trace shape are
  unchanged; an at_depth entry is identifiable by its slot's
  depth and its declared position in preview.
- The other ST-18 insertion positions (before/after example
  messages, Author's Note top/bottom, Outlet) have no attested
  world-info code in-tree (codes 2/3 are not lore positions in
  the corpus) and no native name; they are not modelled.
  Unattested codes still ride the file layer verbatim via
  `position_code` (P-019) and degrade to `before_char` on the
  DB leg, exactly as before.
- No live generation wiring: the generation pipeline still
  does not run lore activation for real chats (no chat↔book
  binding exists yet — the P-033 seam note). The inspector is
  the production-shaped composition path today, and it now
  honours placement; the future pipeline slice composes
  through the same preview fields and `_lore_slot` contract.
- No editor/UI surface: the lorebook editor does not yet
  expose depth/role (P-042 owns editor depth); they are
  reachable through the API, the service, preview, and file
  import today.
- Multiple at_depth entries in one prompt splice in slot
  order under the composer's existing S206 successive-note
  semantics (each later note counts from the tail segment
  left by the earlier one); this slice does not redesign
  that contract.

## Test maintenance

- The P-005/P-019/P-030 dropped-field pins shrink by exactly
  the two fields this slice lands: `depth` and `role` move
  from the dropped sets to the mapped sets —
  `tests/test_p005_interop_corpus.py` (18 → 16 dropped; the
  Gale-Bell now asserts position `at_depth`, depth 4, role
  `system` where it pinned the collapse), 
  `tests/test_p019_lorebook_interop.py` (17 → 15; `gale.role`
  now reads the normalised name `"system"` instead of the
  verbatim code 0, and the DB-path assertion flips from the
  pinned collapse to the real mapping), and
  `tests/test_p030_part2_gate.py` (17 → 15;
  `WORLDINFO_TRANSFER_MAPPED_SOURCE` and `MAPPED_ENTRY_KEYS`
  gain both fields; the store-leg exact entry key set grows
  by `depth` + `role`).
- **F1 closed in the gate battery, deliberately:** the P-030
  store-leg position pin (`gale["position"] == "before_char"`,
  "PINNED LOSS (a), position half") now asserts `at_depth` /
  depth 4 / role `system`, and
  `test_lorebooks_store_leg_native_at_depth_pinned_limitation`
  (which pinned the store refusing the native at_depth book
  whole) is replaced by
  `test_lorebooks_store_leg_native_at_depth_round_trips`: the
  book stores whole, the Ferry reads back at_depth with depth
  None / role `system`, and the store export equals the
  transfer parse exactly. The gate record document
  (`docs/PART_II_GATE_2026-11-06.md`) is a historical record
  and is NOT edited; its F1 text stands as what was true at
  the gate, and this slice is the road it named.
  (`import pytest` left the gate module with its last
  `pytest.raises` gone.)
- Adding migration 0030 moves the schema head, so the head
  pins across the suite move 0028 → 0030 in seventeen test
  files (full revision lists gain `"0030"` after `"0028"` —
  0029 does not exist in this tree; it is P-037's reserved
  number): `tests/test_s103_storage.py`,
  `tests/test_s106_characters.py`, `tests/test_s107_chats.py`,
  `tests/test_s201_lorebooks.py`,
  `tests/test_s210_group_chats.py`,
  `tests/test_s801_archive.py`, `tests/test_s802_restore.py`,
  `tests/test_p021_preset_interop.py`,
  `tests/test_p023_card_assets.py`,
  `tests/test_p025_character_versions.py`,
  `tests/test_p026_scenario_interop.py`,
  `tests/test_p029_provenance_on_import.py`,
  `tests/test_p032_selective_logic.py`,
  `tests/test_p033_timed_effects_persistence.py` (its
  `MIGRATIONS[-4]` 0025 pin moved to `[-5]`, its tail window
  re-based), `tests/test_p034_inclusion_groups.py` (head test
  renamed, tail indices re-based to [-1..-5]),
  `tests/test_p035_entry_states.py` (sequence tail widened to
  five), and `tests/test_p036_probability_rng.py` (head test
  renamed, tail indices re-based, old-DB applied list gains
  0030). Historical pins asserting a migration's own facts
  (0028's column, the gate record's historical text) were
  left untouched. No assertion was weakened.
- Ruff: clean on every file this slice adds or creates; the
  one remaining models.py finding (line 161) is the
  pre-existing P-035 comment, present at the base. In
  `test_p030_part2_gate.py` the slice removed its three added
  findings (unused import, two long comments); the file's six
  pre-existing findings are untouched.

## Evidence

- Battery: 151 passed / 0 failed —
  `tests/test_p038_position_depth.py`
  (`hidden_files/p038_battery.log`).
- Neighbours: 1000 passed / 0 failed — S201–S206, S209,
  S213–S215 lore/prompt pipeline, S103/S106/S107/S210/
  S801/S802 storage/archive, P-005, P-019, P-021, P-023,
  P-025, P-026, P-029, P-030 (gate + stranger library),
  P-031–P-036 batteries and the P-038 battery
  (`hidden_files/p038_neighbours.log`).
- Full suite: recorded in `hidden_files/P038_EVIDENCE.md`;
  no full-suite count is claimed here.

## Carried findings/limitations (honest record)

- Migration 0030 is provisional: 0029 is reserved for the
  concurrent P-037 slice, which banks first. The keeper may
  renumber 0030 (module, REVISION/DESCRIPTION, registration,
  and head pins) at banking. In this worktree the revision
  sequence runs 0028 → 0030 until P-037 banks.
- Gate finding F1 is CLOSED by this slice (both halves: the
  DB store accepts at_depth entries, and code 4 no longer
  collapses on the DB path). The remaining Part II gate
  findings (F2 bulk scenario classification, F3 chat refusal
  text asymmetry, F4 stale manifest prose, F5 character-only
  provenance) are other slices' roads, untouched here.
- The role code table {0 system, 1 user, 2 assistant} is
  Rúnmál's own definition, made by this slice from its own
  role vocabulary; if a future corpus fixture attests a
  different code, the table — and only the table — moves.
- Depth counts SURVIVING history parts: when the composer
  trims old history under budget, an at_depth entry's splice
  point moves with the survivors (the S206 contract, pinned
  there). That is the contract, not a defect.

## Clean-room basis

Built from Rúnmál's own roadmap line, its own S205/S206
composer contract, P-002's census of public documentation
(ST-18: insertion at a chosen in-chat depth with a chosen
role among system/user/assistant), and the public world-info
field names/codes exactly as P-005's authored corpus fixtures
carry them (the Gale-Bell entry: position 4, depth 4,
role 0; the native Ferry: position `at_depth`, no companions
declared). The placement semantics — code table, asymmetric
normaliser fallbacks, effective-default materialisation,
depth-injection ordering — are Rúnmál's own design for the
roadmap line. No SillyTavern or Voxta source was inspected;
the slice's test entries are authored fresh in the test
module (P-005 discipline).

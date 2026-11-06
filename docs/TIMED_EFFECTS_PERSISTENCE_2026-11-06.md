# Timed effects persistence (P-033) — 2026-11-06

Roadmap line: *P-033 Timed effects: sticky/cooldown/delay entries across a chat's life.*

Part III (Lorebook Depth), from
`docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`.
The S203 activation engine already knew how to run sticky,
cooldown and delay counters, but only in memory: callers passed
a state dict in and got it back mutated, and every caller in the
product started from a clean dict and threw the counters away.
This slice is the persistence layer that activation's own module
docstring always pointed at — the counters now survive across a
chat's life, at the database boundary, while `activate()` itself
stays pure and frozen.

## What was built

- Migration 0025 — `src/runmal/db/migrations/m0025_chat_lore_entry_states.py`,
  registered last in `src/runmal/db/migrations/__init__.py`, so the
  schema head moves 0024 → 0025. It creates one table,
  `chat_lore_entry_states`:
  - Composite primary key (`chat_id`, `entry_id`), with
    `chat_id` a foreign key to `chats(id)` and `entry_id` a
    foreign key to `lore_entries(id)`, both `ON DELETE CASCADE`,
    and an index on `entry_id`.
  - The live counters as typed columns: `sticky_remaining`,
    `cooldown_remaining` and `delay_remaining`, each
    `INTEGER NOT NULL DEFAULT 0`; `delay_armed`
    `INTEGER NOT NULL DEFAULT 0` (0/1, the house bool
    convention); and `updated_at TEXT NOT NULL` (ISO-8601 UTC,
    set by the service on every save).
  - Cascades do the deletion work declaratively: deleting a chat
    takes all its state rows with it; deleting a lore entry
    takes that entry's rows in every chat with it; deleting a
    lorebook chains through its entries; deleting a user chains
    through either parent. Editing an entry's timing
    configuration leaves its rows untouched — the new config
    applies on the next arming, exactly as in-memory `activate()`
    behaves.
  - No backfill: every existing chat simply has no rows, which
    *is* the correct pre-P-033 state. No `downgrade()` is
    written, following the forward-only migration runner; the
    table is pure runtime state, so dropping it would lose only
    in-flight counters, never content or configuration.
- ORM — `src/runmal/db/models.py` gains `ChatLoreEntryState`
  (after `ChatSummary`), mirroring the DDL column for column:
  the same composite primary key and cascading foreign keys, the
  three counters as integers defaulting to 0, `delay_armed` as a
  bool (stored 0/1), and `updated_at` as a `datetime` defaulting
  to `_utcnow`. Its docstring carries the DATA_MODEL.md rule:
  the canonical `LoreEntry` row holds sticky/cooldown/delay
  *configuration*; this row holds the live counters. No other
  model changes, and `Chat` gains no state column.
- Persistence service — new module `src/runmal/lorebooks/state.py`,
  the only new runtime code in the slice:
  - Pure serialisation helpers (sync, no database):
    `is_default_state`, `state_to_dict` / `state_from_dict`, and
    `states_to_dict` / `states_from_dict`. The field mapping is
    exact and 1:1 with `EntryState`'s dataclass fields, with no
    renaming. Tolerance is narrow and stated: missing keys fall
    back to the dataclass defaults, unknown keys are ignored
    (forward compatibility), counter values must be non-negative
    ints with bools rejected (mirroring
    `activation._check_non_negative`) or `ValueError` is raised,
    a non-dict raises `ValueError`, and `delay_armed` is coerced
    with `bool()`. A negative counter found in a stored row also
    raises `ValueError` on load — fail loud, never silently
    clamp corruption.
  - The key semantics, which the battery pins: **absence of a
    row means the default state** (all counters 0, unarmed), and
    **default states are never stored**. `states_to_dict` omits
    them, and a save deletes — or never writes — the row for any
    in-scope entry whose state is default. This is load-bearing,
    not cosmetic: `activate()` set-defaults an `EntryState` for
    every non-disabled candidate on every tick, so a verbatim
    save would permanently store one row per scanned entry per
    chat. With the rule, a row exists only while a timed effect
    is actually in flight, and a finished effect cleans up after
    itself on the next save.
  - `load_entry_states(session, user_id, chat_id, entry_ids=None)`
    — read-only, never commits, never writes. Returns `None`
    when the chat is missing or not owned (foreign and missing
    are indistinguishable, the house rule), `{}` when the chat
    is owned but no effect is in flight, and otherwise only the
    rows whose entry still exists: **stale entry ids are
    filtered on load** by joining against `lore_entries`, so
    state orphaned by a pragma-less raw connection or an old
    restore is never resurrected into the live dict.
  - `save_entry_states(session, user_id, chat_id, states, *, entry_ids=None)`
    — scope-synced per (chat, book): `entry_ids` is the
    *complete* scope of the save (default: the keys of the
    states dict), and within (chat, scope) the stored rows are
    made to match the given states exactly — non-default states
    are upserted with `updated_at` refreshed, default or absent
    states have their row deleted. Rows outside the scope
    (other books ticked earlier in the same chat) are untouched,
    except that **stale ids are also swept on save**: rows in
    the chat whose entry no longer exists are deleted as part
    of the same commit (self-healing, belt-and-braces behind
    the FK cascade). Returns `False`, writing nothing, when the
    chat is missing or not owned; otherwise commits and returns
    `True`.
  - `clear_entry_states(session, user_id, chat_id, entry_ids=None)`
    — deletes stored state for a chat and commits: all of it
    when `entry_ids` is `None` (the reset operation a future
    reset slice will want), otherwise only the listed entries.
    `False` for a missing or foreign chat; deleting nothing is
    still `True`.
  - `run_activation_tick(session, user_id, chat_id, book_id, hit_ids, *, recursive_hit_ids=None, hit_depths=None)`
    — the seam a future pipeline slice calls once per generated
    prompt for a real chat. It resolves the owned chat, resolves
    the owned book's entries, loads the persisted states for
    those entry ids, runs the pure `activate()`, then saves the
    resulting states. The save happens **strictly after
    `activate()` returns**, and the tick is **one commit**: if
    `activate()` raises, nothing is saved, so a tick's counter
    movements are persisted all-or-nothing. Returns `None`,
    persisting nothing, when the chat or the book is missing or
    not owned. **Hit computation stays with the caller**: the
    tick takes `hit_ids` (plus the P-031 recursive passthroughs)
    as parameters, because scanning needs messages and
    scan-depth policy that belong to the future pipeline slice;
    a caller with messages can obtain hits today from
    `scan.scan_entries` / `scan_entries_recursive`.
- Documentation of the decision — `docs/DATA_MODEL.md` gains one
  paragraph under Lorebooks naming `chat_lore_entry_states` as
  the separate runtime-state model its existing sticky/cooldown
  paragraph already called for, and stating that preview and
  prompt inspection remain clean-state and never read or write
  these rows.
- New battery — `tests/test_p033_timed_effects_persistence.py`:
  pure serialisation round-trips and tolerance, the migration's
  table shape (columns, both cascading foreign keys, composite
  key, DDL defaults, no backfill), service load/save/clear
  including restart (fresh-session) reads, multi-tick chat-life
  simulations for sticky, cooldown, delay and their interaction
  via `run_activation_tick`, chat and cross-user isolation,
  deletion behaviour, and clean-state neighbour guards.
  "Restart" in the battery means a new session loaded fresh
  from the database — no in-memory dict is carried over.

## What was deliberately NOT wired

- No router endpoint. There is no state-inspection UI, the only
  lore router surface touching activation is the stateless
  preview endpoint, and inventing a REST shape for runtime
  counters now would guess at a future client's needs.
  Load/save/clear are service-level only.
- No generation or prompt-composer hook. `generation/service.py`
  and the prompt composer are untouched: there is still no
  chat↔lorebook binding to tell a live prompt which books apply,
  so the live-generation wiring belongs to the later pipeline
  slice that owns that selection. `run_activation_tick` is the
  seam it will call.
- Preview and prompt inspection stay clean-state, by design and
  forever: `preview.py` and `prompt/inspect.py` are untouched,
  still call `activate()` without a states argument, and never
  read or write `chat_lore_entry_states`. Preview answers "what
  *would* this tick do"; the battery pins that persisted ticks
  do not leak into preview results and that preview writes no
  rows.
- No export/import carriage. Chat export/import and lorebook
  transfer/interop are untouched: runtime state is not portable
  content (the standing precedent is that chat export carries
  messages only).
- No `ChatEvent` is recorded for ticks, and `activation.py`,
  `scan.py`, both service modules and the lorebook router are
  untouched — `state.py` consumes their public functions only.

## Test maintenance

- Adding migration 0025 moves the schema head, so the head pins
  across the suite move 0024 → 0025 in thirteen test files:
  `tests/test_s103_storage.py`, `tests/test_s107_chats.py`,
  `tests/test_s201_lorebooks.py`, `tests/test_s106_characters.py`,
  `tests/test_s210_group_chats.py`, `tests/test_s801_archive.py`,
  `tests/test_s802_restore.py`,
  `tests/test_p021_preset_interop.py`,
  `tests/test_p023_card_assets.py`,
  `tests/test_p025_character_versions.py`,
  `tests/test_p026_scenario_interop.py`,
  `tests/test_p029_provenance_on_import.py`, and
  `tests/test_p032_selective_logic.py`. Only head assertions
  moved in those files (migration lists, `applied[-1]`,
  `current_revision`, archive/restore `schema_revision`, and
  the P-032 head test's own name).
- The DO-NOT-MOVE feature pins were preserved exactly: P-032's
  migration-0024 feature tests (the `selective_logic` column and
  its raw-row default), P-029's migration-0023 feature tests,
  and the P-030 gate record's historical text ("migration head
  remains 0023") are records of their own slices, not live head
  pins. No assertion was weakened.

## Evidence

- Battery: 69 passed / 0 failed —
  `tests/test_p033_timed_effects_persistence.py`
  (`hidden_files/p033_battery.log`).
- Neighbours: 269 passed / 0 failed — S203 activation (17),
  S201 lorebooks (9), S103 storage (6), P-032 selective logic
  (187) and P-031 recursive scanning (50)
  (`hidden_files/p033_neighbours.log`).
- Full suite: pending at time of writing. It is run by the
  tester after this document, and its result is recorded in
  `hidden_files/P033_EVIDENCE.md`; no full-suite count is
  claimed here.

## Carried findings/limitations (honest record)

- Recursive-hit provenance is not carried across ticks: a
  recursive hit on a delay-configured entry only arms the delay,
  and when the entry later fires it reports `via="delay"`,
  depth 0, because `EntryState` carries no pending via/depth.
  This is the pre-existing P-031 limitation, unchanged by this
  slice — persistence stores exactly the four `EntryState`
  counters and nothing more.
- Timed state is effectively per (chat, book) in operation,
  because books bind per request: there is no chat↔lorebook
  binding anywhere, books are chosen per request, and entry ids
  are globally unique with each entry belonging to exactly one
  book. Rows are therefore keyed (chat, entry), the book is only
  the enumeration source for a tick, and each tick's save is
  scoped to that book's entries — one book's tick never disturbs
  another book's in-flight effects in the same chat, and no
  other key is needed.
- Gate finding F1 — a native lorebook carrying `at_depth`
  entries cannot enter the DB store — is untouched. That is
  expressly P-038's road, not this slice's.

## Clean-room basis

Built from Rúnmál's own S203 activation semantics, the
separate-modelling note in `docs/DATA_MODEL.md`, and the public
world-info behaviour already recorded in P-002's census. No
SillyTavern or Voxta source was inspected; the slice's test
entries are authored fresh in the test module (P-005
discipline).

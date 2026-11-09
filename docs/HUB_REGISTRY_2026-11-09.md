# Hub registry: the owner's index of their packs (P-187) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* The roadmap's detailed Part XII text is
not in the repo; Parts VII onward have run DERIVED, and
this opener's scope is derived the same way - see
`hidden_files/P187_SCOUT.md` and `P187_DESIGN.md` in the
team worktree.

## What was built

- `src/runmal/hub/registry.py` - the hub's foundation
  record: an owner-scoped index of the pack artefacts an
  owner holds. An entry carries its kind under the closed
  `HUB_KINDS` law, a title, the operator's locator, an
  optional caller-claimed `content_sha256`, an optional
  note, and its register stamp. Each kind names the
  sealed format it indexes, and `KIND_FORMATS` rides in
  every document:
  - `lorebook_pack` -> `runmal-lorebook-pack` (P-045)
  - `prompt_pack` -> `runmal-prompt-pack` (P-063)
  - `preset_bundle` -> `runmal-preset-bundle` (P-054 share)
  - `scenario_pack` -> `runmal-scenario-pack` (P-141)
- Persistence is the P-117 house pattern as reused by
  P-169: one versioned JSON index (`hub.json`) in the
  data dir, tolerant load - a corrupt store reads as
  empty and never bricks the surface. No migration: the
  schema head stays 0041.
- `src/runmal/hub/router.py` - four roads on `/api/v1/hub`,
  bearer-gated in `app.py` like every API router:
  - `POST /hub/entries` - register (201, entry document;
    422 on a refusal).
  - `GET /hub/entries/{id}` - one entry (404 when unknown
    or foreign; existence never leaks).
  - `GET /hub` - the owner's list document, with an
    optional `?kind=` filter (422 for an unknown kind).
  - `DELETE /hub/entries/{id}` - remove one entry (404
    when unknown or foreign).

## The laws this foundation keeps

- The locator is data (the P-121/P-169 law): it is stored
  verbatim after a strip, registering never claims the
  file exists and never inspects it, and existence is a
  read-time fact judged live on every document under the
  closed `LOCATOR_STATES` law (`ready` / `missing` /
  `not_a_file` / `unreadable`). A state is data at 200,
  never an error, and it is never stored - create the
  file and the same entry's state changes.
- Register refusals are plain and total (nothing stored):
  an empty title, an empty locator, a kind outside the
  closed law, a supplied checksum that is not 64 hex
  digits, and a duplicate (owner, kind, locator) triple.
  Re-registering is remove-then-register, never a silent
  overwrite; the same locator under a different kind or
  a different owner is a different entry.
- The checksum is the caller's claim: shape-checked at
  register time, stored lowercased, and never presented
  as verified - this surface has not read the pack.
  Verification stays with each pack layer's own inspect
  road; signing is later Part XII work.
- Removal is exact: a hit removes exactly that entry; a
  miss removes nothing and writes nothing.
- List counts are computed from the entries themselves:
  total, `by_kind` (every kind in the law, zero-filled)
  and `by_locator_state` (every state, zero-filled).

## The sovereign shape, and what deliberately did not change

- VX-59 rules the hub DELIBERATELY-DIFFERENT: no central
  store, no catalogue, no creator profiles. This registry
  is the owner's own index of their own local packs -
  the foundation the ruled shape (signed local packs,
  friend-instance exchange) stands on.
- Data only: the hub opens no pack, parses nothing,
  copies nothing, imports nothing, installs nothing,
  fetches nothing, reaches no network, runs nothing and
  grants nothing. Inspect and import stay with the pack
  layers' own roads (candidate E in the scout, declined
  with reasons); the `.runmal` archive stays the
  whole-estate backup format and is not a hub kind.
- Named open for later Part XII slices: signing /
  attestation of packs, friend-instance exchange
  transport, hub-side browse over entry contents.
- The P-186 carried items are untouched, exactly as
  recorded: the binding label update stays named open,
  automatic retention / bulk clear of history still
  awaits Volmarr's ruling (none invented), and
  unified-search history stays named open.
- No existing module changed except `app.py` (the router
  wiring); no README touched; no migration.

## Tests

- `tests/test_p187_hub_registry.py` - see
  `hidden_files/P187_EVIDENCE.md` in the team worktree for
  the run counts (battery, neighbours, full suite) read
  back from the log files.

# Hub-side browse over entry contents (P-188) - 2026-11-09

Roadmap line: *Part XII - The Hub, Sovereign Shape
(P-187..P-202).* Part XII's detailed text is not in the
repo; this slice's scope is DERIVED, as P-187's was -
see `hidden_files/P188_SCOUT.md` and `P188_DESIGN.md`
in the team worktree.

## What was built

- `src/runmal/hub/browse.py` - the browse truth layer:
  `browse_document(entry)` (schema
  `runmal-p188-hub-browse-v1`) returns the P-187 entry
  row verbatim, its locator state judged live, and a
  `browse_state` under the closed `BROWSE_STATES` law:
  - `inspected` - the pack was read through its owning
    layer's own verified inspect road and the road's
    document rides verbatim as `inspection`;
  - `unavailable` - the locator is not `ready`
    (missing / not_a_file / unreadable); no read is
    attempted and the locator state names why;
  - `invalid` - the locator was ready but the contents
    could not be browsed (unreadable at read time, over
    the 16 MiB browse bound, or refused by the owning
    road, whose own refusal is carried verbatim as
    `error`).
- Composition, never a second parser - the dispatch is
  exactly the closed `HUB_KINDS` law:
  - `lorebook_pack` -> `lorebooks.packs.inspect_pack`
    (P-045)
  - `prompt_pack` -> `presets.packs.inspect_pack`
    (P-063; the prompt-pack layer lives in presets)
  - `scenario_pack` -> `scenarios.packs.inspect_pack`
    (P-141)
  - `preset_bundle` -> `presets.bundles.parse_share`
    (P-054) - that layer owns no `inspect_pack`; its
    verified share road is the function its own import
    uses first, and the inspection document is built
    only from `parse_share`'s outputs plus the envelope
    manifest fields it just verified.
- `src/runmal/hub/router.py` - ONE new road:
  `GET /hub/entries/{entry_id}/browse`, bearer-gated
  and owner-scoped exactly like the P-187 read road
  (unknown or foreign -> 404 "hub entry not found").
  Every browse state answers 200: states are data,
  never errors dressed as success.

## The laws this slice keeps

- Read-only, total: browse reads the one file at the
  entry's locator and writes nothing - the registry
  file and the pack file are byte-unchanged by a
  browse (pinned in the battery), and nothing is
  imported, installed, copied or granted.
- The checksum law: the entry's stored checksum stays
  the caller's CLAIM. Browse reports the owning road's
  own verified checksum beside it
  (`verified_content_sha256`) and a plain
  `checksum_match` verdict - true or false when both
  sides exist, null when either is absent. A bare
  preset bundle's road verifies no checksum, so the
  verified side is empty and the match is null, stated
  plainly rather than filled in.
- Signing / attestation stays declined: no key
  machinery is banked in-tree, and this slice invents
  none - faking trust would be worse than naming it
  open. Friend-instance exchange transport stays
  declined: no banked pack transport exists (the
  connections layer probes model backends; it is not
  peer pack exchange). Index preceded exchange, and
  browse precedes it too.
- VX-59's shape stands: no central store, no
  catalogue, no creator profiles.
- The P-186 carried items are untouched, exactly as
  recorded: the binding label update stays named
  open, automatic retention / bulk clear of history
  still awaits Volmarr's ruling (none invented), and
  unified-search history stays named open.
- No migration (head stays 0041); no existing module
  changed except the hub router; no README touched.

## Tests

- `tests/test_p188_hub_browse.py` - see
  `hidden_files/P188_EVIDENCE.md` in the team worktree
  for the run counts (battery, neighbours, full suite)
  read back from the log files.

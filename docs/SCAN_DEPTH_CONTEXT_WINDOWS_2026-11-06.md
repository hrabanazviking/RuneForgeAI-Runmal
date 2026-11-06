# Scan depth & context windows (P-037) — 2026-11-06

Roadmap line: *P-037 Scan depth & context windows: per-book
scan settings (messages-deep, whole-chat, external context)
as data.*

Part III (Lorebook Depth), from
`docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`.

## The shallowness this removes

A book's scan window was one bare integer and one silent
assumption:

- `scan_depth` (S201) said how many messages back the scanner
  looked — and that was the whole vocabulary. A book that
  needed its lore checked against the whole chat, however long
  it ran, had no way to say so; the depth was a ceiling no
  setting could lift.
- Context that lives outside the chat message list — a
  character's description, a persona, a scenario: text that is
  in the prompt but is not a message — could never trigger
  lore at all, because the scanner only ever saw messages.
  Whether such context *should* count was not a decision the
  book could record; it was hard-wired to "never".
- Neither behaviour was data. There was nothing to store,
  carry in a file, show in a preview, or explain after the
  fact.

## What was built

- The window module — new `src/runmal/lorebooks/windows.py`,
  pure (no DB, no I/O, no network, no randomness, no
  wall-clock). It owns the per-book scan-settings vocabulary:
  - `scan_depth` — messages-deep, an int >= 1, default 4.
    Meaning unchanged from S201.
  - `scan_mode` — `"depth"` (default: scan the last
    `scan_depth` chat messages — exactly the pre-P-037
    behaviour) or `"whole_chat"` (scan every chat message;
    `scan_depth` stays stored for if the author switches
    back, but does not bound the window).
  - `scan_external_context` — a bool, default False. When
    true, caller-supplied external context texts join the
    window as their own segment, appended after the chat
    segment, NOT counted against the depth (depth counts
    chat messages; the external segment is governed by its
    own flag). When false, supplied external text is ignored
    entirely — never scanned, never reported as scanned.
  - `ScanSettings` — the frozen settings record. Its
    constructor validates strictly (`check_scan_mode`,
    `check_scan_depth`, `check_scan_external_context`);
    `ScanSettings.normalised(...)` and
    `ScanSettings.from_book(...)` build tolerantly for the
    stored/file layers, where unknown or malformed values
    fall back to the defaults — an unknown mode falls back
    to `"depth"`, the narrow pre-P-037 window, never to a
    wider window the author did not ask for (the P-034 /
    P-036 discipline).
  - `build_scan_window(settings, messages, external_context)`
    resolves one tick's window: the chat segment per the
    mode, then the external segment when enabled. Every
    position carries honest provenance — its source
    (`"chat"` / `"external"`), its index in the FULL
    message list, or its index in the external list — and
    `ScanWindow.summary()` reports counts only, never text.
- The scan engine — `scan.py` gains `scan_entries_windowed`,
  which runs the window above through the SAME matching core
  as `scan_entries` (the core was factored into `_scan_texts`
  so the two paths cannot drift; the battery proves
  hit-for-hit equality at five depths). `ScanHit` gains
  `external_indices`: chat matches keep reporting
  `message_indices` into the full message list (the S202
  contract), external matches report indices into the
  caller's external list — where a key fired is never
  ambiguous. Primary and secondary keys may be satisfied
  across segments (the window is one context; the battery
  proves the cross-segment gate both ways, including a
  `not_any` secondary living only in the external segment).
  `scan_entries_recursive` takes `settings` /
  `external_context`: round 0 resolves the book's window,
  later rounds are unchanged. One honesty fix rode along:
  the recursive reconstruction of round-0 (and later-round)
  hits used to drop the hit's `selective_logic` — it now
  carries it, and round 0 carries `external_indices` too.
- Storage — migration `0029` adds `lorebooks.scan_mode`
  (TEXT, default `'depth'`) and
  `lorebooks.scan_external_context` (INTEGER, default 0);
  every existing book reads back with pre-P-037 behaviour
  (the battery upgrades a 0028 database in place and proves
  the row survives untouched). The model, `lorebook_to_dict`,
  `create_lorebook` / `update_lorebook` (strict checks, so
  the API surfaces a bad mode or a non-bool flag as 422),
  and the create/update/preview request shapes all carry
  the two fields. The preview endpoint resolves unset scan
  settings from the book's stored ones, like scan_depth
  before it, and validates an override mode strictly — a
  bad override is a 422, never a silent default.
- Preview & inspector — `preview_activation` takes the
  resolved settings plus `external_context`, runs the
  windowed scan (recursive mode included), and reports
  `scan_mode`, `scan_external_context`, and a `scan_window`
  summary (texts scanned, split chat/external); each hit
  row reports `external_indices`. The prompt inspector
  (`prompt/inspect.py`) now passes the book's stored
  settings into the preview, so the trace honours the same
  window the engine would use — and it supplies the one
  external text that pipeline actually holds, the inspected
  character's persona text, as the external context (a book
  scans it only when its own flag admits it; the battery
  proves the flag-on book fires from the persona text while
  the flag-off book does not).
- File layer — the native shape carries `scan_mode` /
  `scan_external_context` first-class: `transfer.export_book`,
  `parse_import`'s native leg (tolerant normalisation),
  both import paths (`import_book`,
  `import_book_transactional`, with `validate_parsed_book`
  mirroring the strict checks), the interop file model
  (`LorebookFile`, `native_book_fields`, `export_native`,
  `worldinfo_from_native`), and the library duplicate hash
  (two books differing only in scan settings are different
  books). The world-info leg keeps the P-019 discipline:
  book-level settings in a world-info file ride in
  `originalData`, preserved verbatim (the corpus still reads
  `originalData == {"scan_depth": 4}`), and the per-entry
  world-info `scanDepth` field stays preserved-as-data in
  `extra` — P-037's settings are per-book, no per-entry
  semantics are claimed for it, and the P-005/P-030 dropped
  set is unchanged at 17.

## Honest limits

- External context is caller-supplied text. This slice
  defines the setting, the window, and the scan; deciding
  WHICH texts a given chat hands the scanner as external
  context (character description, persona, scenario) is the
  caller's composition choice — the preview and API accept
  the texts, the prompt inspector supplies the inspected
  character's persona text, the engine scans what it is
  given, and the window summary says how much of each kind
  was scanned.
- The lorebook editor UI does not yet expose the two new
  settings; reaching every engine field from the editor is
  P-042's road, as with the other Part III fields.
- Whole-chat scanning is linear in chat length, like the
  depth scan is in depth; the 10,000-entry performance
  budget is P-046's road.

## Verification

- Battery: `tests/test_p037_scan_windows.py` — 47 passed
  (vocabulary strict/tolerant pairs, window builder,
  windowed-vs-plain hit equality at five depths, whole-chat
  reach, external hits + cross-segment gates, recursive
  round 0, preview reporting, service/API round trips +
  422s, migration 0029 + in-place upgrade, native transfer
  + interop round trips, corpus preservation, library hash,
  prompt inspector).
- Neighbours: 832 passed (the P-005..P-036 batteries, the
  S-series lorebook/scan/editor/storage suites, the Part II
  gate, archive/restore).
- Full suite: 1742 passed, 4 skipped, 0 failed.

# Book sharing: lorebooks as importable packs (P-045) — 2026-11-06

Roadmap line: *Book sharing: lorebooks as importable packs
(Part XII's hub carries them).* Part III (Lorebook Depth).

## What was built

- `src/runmal/lorebooks/packs.py` — the pack layer over the
  existing lorebook roads. A pack is ONE lorebook as a
  self-contained, importable file: export a book as a pack,
  hand the file to another Rúnmál instance (or keep it), and
  import it whole there — contents proven intact by checksum,
  origin stated in an honest provenance record, and no
  existing book ever silently overwritten.
  - Envelope: `{"format": "runmal-lorebook-pack",
    "pack_version": 1, "kind": "lorebook", "schema":
    "runmal-p045-lorebook-pack-v1", "manifest": {...},
    "provenance": {...}, "lorebook": <payload>}`.
  - The payload is the UNCHANGED native shape
    (`transfer.export_book`): import parses it with
    `transfer.parse_import` + `validate_parsed_book` and
    writes through the transactional P-022 import
    (`import_book_transactional`). No parallel lorebook
    format was invented. A file-layer book packs too:
    `build_pack_from_file` wraps `interop.export_native`'s
    output, so a world-info file's natively-modelled
    contents can travel as a pack.
  - Manifest: book name, entry count, `content_sha256`,
    `payload_canonical_bytes`, export stamp, app version,
    and the payload's own format/version — each verified
    against the payload at parse time.
  - `parse_pack` / `inspect_pack`: full validation before
    any write exists (envelope, version, manifest, checksum,
    provenance presence, payload importability). Inspect is
    the hub's pre-flight: valid + manifest + provenance +
    verified checksum, as data, with nothing imported.
  - `import_pack` returns (book, report): the report carries
    the manifest and the pack's provenance verbatim, the
    outcome (`created` / `duplicate_exact` /
    `name_collision`), the book id and the real entry count.
- `src/runmal/lorebooks/router.py` — three routes, the two
  POSTs registered before the `/lorebooks/{book_id}` family:
  - `GET /lorebooks/{book_id}/pack` — export one book as a
    pack (404 for an unknown book, owner-scoped).
  - `POST /lorebooks/import-pack` — import a pack whole;
    201 when a book is created, 200 when the pack is an
    exact duplicate of an owned book; `?on_conflict=reject`
    refuses a same-name collision instead of creating.
  - `POST /lorebooks/pack/inspect` — validate + report,
    no write (422 for a tampered or malformed pack).

## Format decision and its reasons

A single JSON envelope — not a `.runmal` archive, not a bare
native export:

- A lorebook is one aggregate (book settings + entries, no
  binary assets), so the ZIP/member machinery of the
  portable archive (`runmal.portable.archive`, S801) buys
  nothing here. That archive stays the whole-library backup
  format; the pack is the single-book sharing format, and it
  composes the archive's discipline (manifest, SHA-256 over
  the contents, validation before any write) without its
  container. Part XII's hub (P-187..P-202) — signed local
  packs and friend-instance exchange, the sovereign shape
  ruled in the DELTA_TABLE (VX-59), not a central store —
  carries this one file unchanged when it lands.
- A bare native export carries no checksum and no
  provenance: a shared file could be silently altered and
  its origin silently lost. The envelope adds exactly those
  two things around the unchanged payload.
- The checksum is defined over the payload's NORMALISED
  form — the (book, entries) `transfer.parse_import`
  produces, entries sorted by canonical JSON — so identity
  means "what an import would actually store": entry order
  and cosmetic spellings the import path normalises away
  (a default spelled out, the store's `useProbability`
  folding) never mint a false different-book, and the
  checksum is stable across a database round trip. It
  covers the normalised payload, never the pack file
  bytes; re-serialising a pack does not invalidate it.
  `payload_canonical_bytes` rides as a cheap hub-side
  size check.

## Provenance and collision discipline

- Provenance mirrors P-029's honesty rules:
  `provenance_version`, `source_kind`
  (`lorebook_pack_export`), the source book's id + name when
  the export came from a stored book, `exported_at`, the
  exporting app version, and the content checksum. Unknown
  facts are OMITTED, never fabricated (a pack built from a
  bare payload or a file carries no `source_book_id`); a
  caller's `note` rides only when one was supplied. Unknown
  keys in an incoming pack's provenance are returned
  verbatim in the import report — carried, never
  interpreted. Provenance is NOT stored on the lorebook
  row (no migration; head stays 0032): its carriers are
  the pack itself and the import report.
- Never silently overwriting (the P-025 precedent,
  adapted): lorebooks have no version lineage, so import
  NEVER merges into or overwrites an existing book. An
  exact duplicate (same owner, same content checksum)
  writes nothing and returns the existing book — first
  copy wins, as with P-025's duplicate cards. A same-name
  import with different contents creates a FRESH book
  under the default `create_new` (report flags
  `name_collision`; no name is suffixed, no version
  minted — the books are told apart by id and checksum)
  or refuses under `reject`. The duplicate scan is
  owner-scoped: another owner's identical book never
  counts, so a shared pack always imports as the
  receiver's own copy. Known limit, stated plainly: the
  check-then-create is not transactional across two
  concurrent imports of the same pack (no unique
  constraint exists to lean on without a migration);
  racing imports can both create.

## Safety

Byte/str input decodes via `runmal.safety.safe_json_loads`
under the lorebook file cap (32 MiB,
`interop.MAX_LOREBOOK_BYTES`); decoded input passes
`validate_json_tree`; the payload passes the import path's
own validation before any write, and the write is the
transactional import, so a pack that fails anywhere leaves
nothing behind.

## What deliberately did not change

- `transfer.py`, `interop.py` and the `.runmal` archive
  are untouched; the existing `/lorebooks/import` and
  `/lorebooks/{id}/export` shapes are unchanged.
- No migration: the schema head stays 0032. No lorebook
  versioning was added (that concept belongs to character
  cards, P-025); packs record identity by checksum instead.
- Signing/encryption of packs and the hub itself are Part
  XII's work (P-187..P-202); this slice builds the pack
  those slices will carry.

## Tests

- `tests/test_p045_lorebook_packs.py` — see
  `hidden_files/P045_EVIDENCE.md` in the team worktree for
  the run counts (battery, neighbours, full suite) read
  back from the log files.

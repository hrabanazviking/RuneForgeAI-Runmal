# Chat Import Surgery (P-078) — P-020's imports become fully live chats

P-020's file layer parses ST-shaped JSONL and Runmal native
exports into the typed `ImportedChat` contract — as DATA. This
slice is the surgery that makes those imports LIVE: a new
service-layer module, `runmal.chats.liveimport`, writes an
imported chat into ordinary `Chat`/`Message` rows in ONE
transaction, after which the chat is indistinguishable from a
native chat on every road: list/get, append, edit, swipe
add/select/delete, fork (branches), checkpoint, search,
export, undo (the journal before-images are taken by those
later operations themselves), and provenance reads.

No router endpoint is added: P-020's file layer is exposed at
the service layer only, and P-078 follows that pattern. The
module's three entry points (`plan_import`,
`materialise_import`, `import_chat_file`) are exported from
`runmal.chats` alongside the P-020 parse functions.

## Deck resolution (per message, deterministic)

- No explicit swipes carried: deck is `[content]`, active 0,
  counted as `messages_without_swipes`.
- Explicit swipes: empty-string alternates are dropped (the
  live deck rejects them) and the source message index is
  reported once in `empty_alternates_dropped`. When `mes`
  disagrees with the active swipe (MES_SWIPE_MISMATCH), `mes`
  is authoritative (filebridge law): if `mes` already exists
  elsewhere in the deck the active index moves to it and
  nothing is lost; otherwise the active slot is replaced by
  `mes` and the displaced alternate is reported via
  `mes_mismatch_repaired`, and the replace case also records
  the displaced alternate's original deck index in
  `displaced_alternates`. The result invariant is exactly
  what the live deck requires: `deck[active] == content`,
  every entry a non-empty string.
- `swipe_info` has no live column (P-065 decks are text-only):
  counted per message as unmappable. `extra` has no live
  column: its KEY NAMES only are reported per message —
  never values, never message text, in the report or in
  events.
- Parsed send dates become `created_at` VERBATIM — no
  timestamp is ever rewritten; display order is guaranteed
  by position. Raw-only/unparsed dates are counted as
  `send_date_unmappable` — never faked. (An earlier draft
  bumped shared timestamps by 1 ms to manufacture order;
  the post-build review removed it as a fabrication.)
- A message with empty content cannot be a live message (the
  append road refuses empty content). It is NOT imported and
  NOT given invented text: its source index is reported in
  `empty_content_refused` and every other message imports,
  renumbered contiguously.

## Branches are never fabricated

The ST shape carries branch structure ONLY as header
`chat_metadata` link keys (`parent_chat`, `parent_chat_id`,
`branch_of`, `branch_point`, `checkpoint_of`, `main_chat`)
naming files/ids of the SOURCE system. Those are not Runmal
chat ids and no mapping exists, so the lineage columns are
never filled from them: the imported chat is `kind=root`,
the declared linkage is preserved verbatim as data in the
report (`declared_branch_link`), and the `chat.imported`
event records only the key names. Once live, the chat forks,
merges, and checkpoints like any native chat. Native exports
carry live branch info only via `chat_to_dict`, not via
`service.export_chat`, so a native re-import likewise reports
branch linkage absent unless the document carries it.

## Provenance (P-075)

Every imported message gets a recorded provenance document:
one record per swipe index, `origin_kind="imported"` with the
scalar origin facts `{source_shape, has_explicit_swipes}`.
The file does not say which model produced the text, so the
model section is an honest gap — `unknown` for assistant
lines, `not_applicable` for user/system lines; the preset is
`unknown`; lore is `unknown` (import ran no lore scan). The
speaker NAME rides the message row as a snapshot
(`speaker_id` stays None — a name in a file is not a Runmal
speaker id).

## Character and title

`character_id` is caller-supplied only and must name a
character the caller owns (`KeyError` otherwise, mirroring
`create_chat`); a character NAME carried by the file is never
guessed into an id. Title: the explicit argument when given,
else the native document's title, else `""` — metadata
generation is a separate road, not import's job.

## In-slice defect fixes

- `fileimport._parse_native` dropped the `swipes`/`swipe_id`
  that `service.export_chat` emits per message, so a native
  round-trip silently lost every deck. The native parser now
  reads a validated deck (string members only, `swipe_id`
  coerced and clamped like the JSONL road) with `content`
  authoritative. Documents without decks parse exactly as
  before.
- `branches._copy_message` dropped the source's swipe deck
  and collapsed provenance to swipe 0, so forking ANY chat
  silently destroyed its decks. It now mirrors
  `service.copy_message_to_branch`: deck, active index,
  variant history, and the full per-swipe provenance (as
  `copied` records) ride along. This is copy-side only — it
  fabricates no lineage; the fork operation itself sets the
  branch's lineage columns, as it always did.
- Review fixes (post-build adjudication, all pinned by
  battery tests): unmappable-metadata accounting now runs
  for refused messages too, and recognises the native
  shape's `created_at`; a MES mismatch whose active
  alternate was a dropped empty is now reported; the
  returned report no longer carries the working plans
  (message text) — `materialise_import` clears them;
  non-string deck entries are dropped by deck resolution;
  a native entry with empty content and a carried deck
  recovers the deck's active text instead of destroying
  it; and branch copies now carry prefix positions with
  `branches._history` ordering position-first, so forking
  a mixed dated/undated import keeps display order.

## Events, migration, honesty

Materialisation records exactly one `chat.created` and one
`chat.imported` event; the import event carries counts and
branch-link key names only. Migration: NONE — every column
used already exists (0036 decks, 0037 lineage, 0040
provenance); head stays 0040.

What the source formats do NOT carry, stated plainly: no
model identity for imported text, no preset, no lore-scan
result, no live speaker ids, no mappable branch lineage,
and no home for `swipe_info` or `extra` payloads. P-078
reports each of those instead of inventing them. P-029's
provenance-on-import remains character-only; this slice's
per-message provenance is new and separate.

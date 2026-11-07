# Author's note depth (P-056) — 2026-11-07

Roadmap line: *Author's note: a per-chat note pinned into the
prompt at a chosen depth, firing on a chosen frequency.*
Part IV (Prompt & Sampler Depth).

## What was built

- `src/runmal/prompt/authors_note.py` — the author's note as
  data, nothing more. `AuthorsNote` is the validated value
  object: `text`, `depth` (default 4), `frequency` (default 1),
  `enabled` (default true), `role` (default `system`; one of
  `system` / `user` / `assistant`). `note_from_data` /
  `note_to_data` are the strict boundary with stored / supplied
  data: unknown keys, wrong types (a `bool` is not an `int`),
  `depth < 0`, and `frequency < 1` all raise `ValueError` — a
  malformed note is refused, never repaired silently and never
  partially applied. `None` data means no note was stored and
  yields the default (empty) note. `has_content` is true only
  for an enabled note with non-blank text; a blank or disabled
  note is inert.
- `slot_for(note, message_count)` builds the composer's slot
  when — and only when — the note is active: kind
  `authors_note`, id `authors_note/chat`, provenance
  `chat:authors_note`, spoken in the note's role, carrying the
  note's `depth`. The existing machinery does the rest: the
  P-049 layout lift raises a depth slot to just after history,
  and the composer splices it into the surviving history under
  the S206 contract.
- Persistence: `Chat.authors_note_json` holds the whole note
  as ONE validated canonical JSON document (the `PresetBundle`
  aggregate precedent — splitting it across columns would
  invite partial writes that lose carried fields). `{}` is the
  no-note default: an absent note and an empty note are the
  same thing. A corrupt stored document reads as the default
  note rather than failing the read. See the migration note
  below — its number is PROVISIONAL.
- `src/runmal/chats/service.py` / `router.py` —
  `chat_to_dict` always carries `authors_note` (the default
  note for a chat that never set one).
  `POST /chats/{id}/authors-note` validates and stores the
  note (422 on invalid data, storing nothing; 404 on a missing
  or foreign chat) and records an `authors_note.changed` event
  whose data is `{depth, frequency, enabled}` only — never the
  note text, never the role. `GET /chats/{id}/authors-note`
  returns the note itself.
- `src/runmal/prompt/inspect.py` — when a `chat_id` is given,
  the chat's stored note joins the inspector's composition
  (the inspector is the stored-data composition path): an
  active note becomes the depth slot above; a note silenced
  by its frequency surfaces in the Prompt Trace as a discard
  with reason `authors_note_frequency`; a note in a block the
  supplied prompt layout disables surfaces with reason
  `prompt_manager_disabled`, like any other block's slots.
  The result carries an `authors_note` echo (see Honesty).
- `src/runmal/prompt/__init__.py` — the note names join the
  public surface.

## Semantics: depth and frequency

- Depth is the S206 splice count: the note is inserted
  `depth` messages back from the end of the surviving history.
  Depth 0 lands immediately after all history; depth 2 lands
  with the last two history messages after it; a depth larger
  than the history lands before the history. With no history
  at all the composer falls through to plain emission at the
  note's baseline position, as it already does for any depth
  slot.
- Frequency is how often the note fires, counted against the
  composition's message count: the note is active when
  `message_count % frequency == 0`. Frequency 1 therefore
  means every composition. Frequency N > 1 means only every
  Nth composition — and because 0 is a multiple of every N,
  a frequency-N note IS active on an empty (zero-message)
  composition. A note that is not due is not weakened or
  truncated; it is simply absent, and the trace says why.

## Persistence — migration 0034 (PROVISIONAL)

PROVISIONAL 0034: this number is PROVISIONAL. P-055 banks in
parallel with its own migration claim, and the keeper
reconciles numbering at banking — if P-055 takes 0034 first,
this slice's module is renumbered (revision, filename, and
registration) by the keeper before either slice lands. Do
not treat "0034" here as final. The migration itself adds
`chats.authors_note_json TEXT NOT NULL DEFAULT '{}'`,
guarded by a column check so re-running it is a no-op (the
runner's own bookkeeping also makes it idempotent).

## Honesty notes

- The `authors_note` echo in an inspect result is metadata
  only: `{present, active, depth, frequency, enabled,
  message_count, source}`. `present` is `has_content` (an
  enabled, non-blank note exists); `active` reports whether
  the note fired for this composition's message count — it is
  computed before any prompt-layout application, so a note
  the layout then disables reads `active: true` in the echo
  AND `discarded / prompt_manager_disabled` in the trace;
  both statements are true, about different stages. `source`
  is `"chat"` when a `chat_id` was given, `"none"` otherwise
  (with the default note's depth/frequency reported).
- Neither the Prompt Trace nor the echo ever carries note
  text (the S214 contract: traces carry no prompt content).
  The battery pins this by serialising whole inspect results
  and asserting the note text appears nowhere in them, on the
  included, frequency-discarded, and layout-discarded paths
  alike. The chat event log follows the same rule (above).
- The inspector is the composition path for stored notes.
  `tools/service.py compose_preview` keeps its separate,
  older ephemeral note: a caller-supplied string composed
  statelessly with slot id `"note"` and default depth 0, no
  persistence, no frequency, no chat lookup. The two are not
  the same feature and neither pretends to be the other.
- Wiring the stored note into live generation is not claimed
  here: P-056 stores the note per chat and honours it in the
  inspector, the same explicit-input road P-049..P-054 used.

## Clean-room

Built from the roadmap line and Rúnmál's own slot/composer
contracts alone; no third-party author's-note implementation
was copied or consulted.

# Post-history instructions (P-057) — 2026-11-07

Roadmap line: *Post-history instructions (the jailbreak-position block,
neutrally named) as a prompt-manager citizen.* Part IV (Prompt &
Sampler Depth).

"Post-history instructions" is the neutral Rúnmál name for the block
the mirrors place immediately after the conversation history — the
position their ecosystems informally call the jailbreak position,
because an instruction there speaks with the last word before the
model answers. Rúnmál keeps the neutral name and makes the position
itself the contract (see Semantics).

## What was built

- `src/runmal/prompt/post_history.py` — the post-history instructions
  as data, nothing more. `PostHistoryInstructions` is the validated
  value object: `text`, `enabled` (default true), `role` (default
  `system`; one of `system` / `user` / `assistant`). There is
  deliberately NO `depth` and NO `frequency` field (contrast the
  author's note, P-056): the position IS the contract, so there is
  nothing to tune. `instructions_from_data` / `instructions_to_data`
  are the strict boundary with stored / supplied data: unknown keys,
  wrong types, and an unknown role all raise `ValueError` — malformed
  instructions are refused, never repaired silently and never
  partially applied. `None` data means no instructions were stored
  and yields the default (empty) instructions. `has_content` is true
  only for an enabled instructions value with non-blank text; a blank
  or disabled value is inert.
- `slot_for(instructions, source)` builds the composer's slot when —
  and only when — the instructions are active: kind `post_history`,
  id `post_history/<source>`, provenance `<source>:post_history`,
  spoken in the instructions' role, carrying NO depth (`Slot.depth`
  stays `None`, so the S206 depth lift never applies to it). The only
  legal sources are `chat` and `character`; any other source raises
  `ValueError` before the content check.
- Prompt-manager citizenship (`src/runmal/prompt/manager.py`,
  P-049's manager): `post_history` is now a managed block — the
  TENTH block, last in `BLOCK_ORDER`. `block_for_kind("post_history")`
  returns `"post_history"`. Everything else follows from the existing
  machinery: disabling the block drops the slot (the caller records
  the trace discard with reason `prompt_manager_disabled`), and
  reordering the block moves the slot — reordering is the user's
  explicit instruction, exactly as for every other block since P-049.
- Persistence: `Chat.post_history_json` holds the whole instructions
  value as ONE validated canonical JSON document (the `PresetBundle`
  aggregate precedent — splitting it across columns would invite
  partial writes that lose carried fields). `{}` is the
  no-instructions default: absent instructions and empty instructions
  are the same thing. A corrupt stored document reads as the default
  instructions rather than failing the read. See the migration note
  below — its number is PROVISIONAL.
- `src/runmal/chats/service.py` / `router.py` — `chat_to_dict` always
  carries `post_history` (the default instructions for a chat that
  never set any). `POST /chats/{id}/post-history` validates and
  stores the instructions (422 on invalid data, storing nothing; 404
  on a missing or foreign chat) and records a `post_history.changed`
  event whose data is `{enabled, role}` ONLY — never the instruction
  text. `GET /chats/{id}/post-history` returns the instructions
  themselves. (Full mounted paths: `/api/v1/chats/{id}/post-history`.)
- `src/runmal/prompt/inspect.py` — when a `chat_id` is given, the
  inspector resolves post-history instructions and appends the slot
  after the history slot, before the layout / context-template
  stages, so the existing pipeline governs it with no new wiring.
  Resolution precedence: **chat > character card > none** — a
  chat-stored value WITH content wins; else the character card's
  `post_history_instructions` field (a bare text field, so the
  candidate takes the defaults enabled / `system`) becomes the slot
  with source `character`; else there is no slot. A disabled or blank
  chat value does NOT shadow a character card that has content. The
  result carries a `post_history` echo (see Honesty).
- `src/runmal/prompt/__init__.py` — the new names join the public
  surface: `PostHistoryInstructions`, `instructions_from_data`,
  `instructions_to_data` unqualified, and `has_content` / `slot_for`
  ALIASED as `post_history_has_content` / `post_history_slot_for`
  (the unqualified names remain the author's-note ones once P-056
  merges; rebinding them would silently change P-056's surface).

## Semantics: position

- The position IS the contract: after history, baseline-last.
  `post_history` is baseline index 9 — the last slot kind in the
  baseline assembly — and the slot composes after all history at
  baseline. There is no depth (it never splices INTO history) and no
  frequency (it is not gated on message count; an active value fires
  on every composition).
- Default-layout identity: making the block managed does not move it
  by default. Under the old unmanaged tail the order computed as
  `len(blocks) * 100 + baseline_index` = `9 * 100 + 9 = 909`; as the
  managed 10th block (position 9) it computes as
  `9 * 100 + 9 = 909`. Same value, new meaning — the default layout
  remains an exact identity on the baseline assembly.
- What citizenship changes: the block can now be DISABLED (the slot
  drops, with the honest trace discard) and REORDERED (the slot
  follows its block position — even before history, if the user puts
  it there; that is their explicit instruction and no guard or clamp
  is added). The context-template layer may also drop or wrap it via
  the pre-existing `post_history` segment, with reason
  `context_template_disabled`.

## Persistence — migration 0035 (PROVISIONAL)

PROVISIONAL 0035: this number is PROVISIONAL. P-056 (team-03) holds
provisional 0034 (`chats.authors_note_json`) and banks BEFORE this
slice; the keeper reconciles numbering at banking and inserts 0034
before 0035 in the migration registry so registry order stays
revision order (in this interim tree 0035 sits directly after 0033
because 0034 is not here yet — expected pre-merge, not to be banked
as-is). If reconciliation renumbers, the revision string, the module
filename (`m0035_chat_post_history.py`), the registration, the model
comment, and every "0035" test pin move together. Do not treat
"0035" as final. The migration itself adds
`chats.post_history_json TEXT NOT NULL DEFAULT '{}'`, guarded by a
column check so re-running it is a no-op (the runner's own
bookkeeping also makes it idempotent).

## Honesty notes

- The `post_history` echo in an inspect result is metadata only:
  `{present, enabled, role, source}`. `present` is `has_content` of
  the RESOLVED instructions, computed before any prompt-layout
  application, so instructions the layout then disables read
  `present: true` in the echo AND `discarded /
  prompt_manager_disabled` in the trace; both statements are true,
  about different stages. `source` is `chat`, `character`, or `none`;
  when nothing resolves, the echo reports the defaults
  (`enabled: true`, `role: "system"`, `source: "none"`).
- Neither the Prompt Trace nor the echo nor the chat event ever
  carries instruction text (the S214 contract: traces carry no prompt
  content). The battery pins this by serialising whole inspect
  results and the event log and asserting the text appears nowhere in
  them, on the included, layout-discarded, and context-discarded
  paths alike. The text appears only in the composed slot itself and
  in the sanctioned `chat_to_dict` / GET shapes.
- The inspector is the composition path for stored instructions.
  Wiring them into live generation is not claimed here: P-057 stores
  the instructions per chat (with the character-card fallback) and
  honours them in the inspector, the same explicit-input road
  P-049/P-054/P-056 used. Group chats do not resolve them, and only
  the explicit `character_id` input (not the chat's bound character,
  not a persona character) feeds the character fallback.

## Out of scope / deliberately untouched

- `src/runmal/prompt/context.py` is NOT touched. Its `post_history`
  segment and the `jailbreak` story-string alias pre-exist (P-051);
  P-057 only gives that segment a real slot to govern. (Known stale
  cross-reference, left deliberately: context.py's docstring still
  calls post_history "the extra anchor P-049 left unmanaged" —
  historically true of P-049, now superseded by this slice.)
- Preset bundles (P-054) gain NO post-history carriage: `bundle_json`
  has no `post_history` key and overrides cannot set one. The one
  mechanical side effect: bundles store a `prompt_layout` validated
  through `layout_from_data`, so a bundle written with a stored
  9-block layout normalises to the 10-block form (post_history filled
  in, enabled, at the end) the next time it is validated/stored. No
  bundle data is lost. Likewise any stored 9-block prompt layout
  anywhere normalises to 10 blocks on validation — fill-missing is
  the standing back-compat contract.

## Clean-room

Built from the roadmap line and Rúnmál's own slot/composer/manager
contracts alone; no third-party post-history implementation was
copied or consulted.

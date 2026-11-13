# P-149 - Chat Delete-Impact Preview (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-131..
P-148 precedents. The derivation rests on Runmal's own
in-tree record only (full weighing in the team's
scout/design record, hidden_files/P149_SCOUT.md and
P149_DESIGN.md).

Base: c66c5bf (P-147 banking record; P-001..P-147
banked plus one commissioned slice). P-148 (binding
chat-custody census, team-03) is banking concurrently
ahead of this slice and is NOT in this base; its scout,
design and battery were read read-only in the team-03
worktree so this slice neither duplicates nor collides
with it: P-148 adds chatcensus.py and GET
/scenarios/bindings/chat-census (a global pure read,
after the fact), while this slice adds
chatdeletepreview.py and GET
/scenarios/bindings/{chat_id}/delete-impact (a
per-chat pure read, before the act). The router.py,
scenarios/__init__.py and clean-room edits are additive
in disjoint blocks, and the keeper reconciles the union
at banking (P-148 before P-149). Migration: NONE - head
stays 0041. No storage-shape change, no new store, and
- stated plainly - no write-behaviour change anywhere:
the delete_chat cascade was weighed and NOT taken (see
the weighing); chats.service.delete_chat is untouched
and its current custody behaviour is pinned by this
slice's battery exactly as it stands.

## The weighing

- **Chat delete-impact preview - taken.** Part IX's
  irreversible acts each have a pre-commit preview
  except one. Definition deletion has P-139's
  delete-impact preview; definition replacement has
  P-140's impact preview and the candidate previews
  P-146 (definition-side) and P-147 (chat-scoped);
  binding itself has P-136 (definition-side) and P-138
  (chat-scoped). Chat deletion - the chats subsystem's
  irreversible act - has none on the scenario side.
  chats.service.delete_chat cleans, one by one, the
  chat's checkpoints, databank, undo store, vision
  links, image attachments (P-120 custody) and
  folder-watch registrations (P-121 custody) - and
  never the scenario binding store (verified in code:
  no reference to the binding store exists anywhere
  under src/runmal/chats/). A deleted bound chat's
  binding record therefore stands forever, and until
  P-148 no surface named the orphans at all. P-148's
  census names them AFTER the fact, across the whole
  store; the pre-commit half - what deleting THIS chat
  would orphan, judged before the act - had no road.
  That is the exact shape P-139 filled for definition
  deletion, transposed to the chat axis. The preview
  joins the two custody axes for the one chat: the
  chat's existence (owner-scoped, the law bind and
  P-138 read the Chat table by) and the standing
  binding's definition-axis state (P-144's law:
  current, superseded, ahead, stale).

- **Wiring delete_chat to cascade the binding record -
  weighed honestly, NOT taken.** This is P-148's named
  open question, and it stays open here, for reasons
  the record itself supplies. (1) It is a
  write-behaviour change inside the chats subsystem,
  not a scenario read surface; every Part IX slice so
  far has stayed inside its own subsystem, and the
  P-120 / P-121 custody blocks were added by
  chats-line work whose scope was chat custody, not by
  an outside subsystem editing chats.service from a
  neighbouring line. (2) P-148's scout reserved the
  decision expressly: "whether chat deletion should
  unbind is a behaviour decision no in-tree record has
  taken" - named as the honest next question if
  Volmarr wants the cascade. A keeper slice does not
  take a reserved behaviour decision unilaterally.
  (3) The definition side's no-cascade law is
  deliberate (P-132 / P-139): a binding outlives its
  definition stale and named, never silently erased,
  because the binding record is the only surviving
  account of what a binding seeded - its cast, its
  pinned revision, its seeded and skipped lists.
  Chat deletion's custody blocks run silently and
  best-effort (each swallows every exception and
  returns no answer), so a cascade wired there would
  erase that account with no answer, no record and no
  undo. The asymmetry that favours a cascade - the
  chat is gone, so the record has no living subject -
  is real, and the preview states it plainly (the
  seeded messages die with the chat while the record
  that accounts them survives); it is a reason for
  Volmarr to take the decision, not a licence for this
  slice to take it for him. (4) delete_chat's custody
  is selective, not general, in the record: each
  addition was separately commissioned (P-120, P-121),
  and the P-093 chat variables a binding seeds are not
  cleared by delete_chat at all - there is no general
  cascade law to extend mechanically. What this slice
  does instead: it names, before the act, exactly what
  a cascade WOULD remove, and its battery pins today's
  behaviour on both sides - delete_chat leaves the
  binding document byte-untouched; the orphan remains
  removable per chat by the standing unbind road.

- **Joint two-axis global census - declined for this
  slice.** P-144 judges the definition axis globally
  and P-148 the chat axis globally; a joint
  classification is a real composition, but P-148 is
  not in this base - building it here would duplicate
  P-148's chat-axis law in a second module on the eve
  of its banking. The per-chat preview composes the
  two axes for one chat using only in-base verbs
  without duplicating either census.

- **Organisation orphan census - declined, standing.**
  Orphaned organisation rows are filtered at every
  read (P-134), P-139 names the row per definition
  before a delete, and censuses name, never repair;
  cleanup tooling remains declined. The chat axis,
  where a live read surface answers an orphan exactly
  as if its chat lived, is the sharper custody gap.

- **Unbind-impact preview - declined, standing.**
  Unbind's own answer states its one fact - the record
  goes, seeded content stays.

- **Candidate create preview - declined, standing**
  (P-148's weighing): create is neither permanent nor
  destructive, and the stateless P-026 import road
  already dry-reads a body before it is stored.

- **Portable-archive inclusion of the scenario
  stores - declined for this slice** (portable-
  subsystem line, named open there).

- **Playback / runtime / condition evaluation /
  scripting EXECUTION - declined ABSOLUTELY** (P-027
  law: stored content is data, never code).

## The contract

- `src/runmal/scenarios/chatdeletepreview.py` (new) -
  the async read service.
  `preview_chat_delete_impact(session, bindings,
  definitions, owner_id, chat_id)` returns the
  envelope or None. None means the caller holds
  neither an owned chat with this id nor a binding
  naming it: an unknown chat, another owner's chat
  with no binding of the caller's, and a foreign
  binding's chat answer exactly alike, so existence
  never leaks on either side. A binding of the
  caller's is the caller's own fact and answers even
  when its chat is already gone or was never theirs.
- The envelope: `chat_id`; `chat_exists` (owner-scoped
  existence in the live Chat table); `binding` -
  P-132's full record verbatim (the per-chat read's
  own shape), or None for an owned unbound chat;
  `binding_state` under P-144's state law (current /
  superseded / ahead / stale), with
  `definition_exists`, `definition_current_revision`
  and `definition_current_name` beside it (all None
  when there is no binding); `impact` -
  `binding_would_orphan` (a standing binding on a
  living chat), `binding_already_orphaned` (a standing
  binding whose chat is already gone),
  `seeded_message_count`, `seeded_key_count` and
  `cast_count`, each read from the record itself (all
  zero in the honest-zero envelope); and five standing
  honesty notes in fixed order (preview-only pure
  read; today's no-cascade law and the after-the-fact
  census beside this before-the-fact preview; the
  cascade decision open and untaken, with its reasons;
  the seeded-content asymmetry; scenario-custody scope
  only, and truth-as-data).
- One additive road: `GET
  /scenarios/bindings/{chat_id}/delete-impact`,
  declared after the per-chat binding GET / DELETE
  roads. A two-segment suffix cannot be captured by
  the one-segment {chat_id} roads, and it does not
  touch P-148's one-segment literal `chat-census`
  road. The handler takes the session through
  get_session and maps the service's None to 404
  "chat not found" (the P-138 / P-147 chat-side
  detail). No other 404 case: an owned unbound chat
  answers the honest zero at 200, and an
  already-orphaned binding answers at 200.
- `src/runmal/scenarios/__init__.py` (additive) - a
  subsystem-map bullet for chatdeletepreview after the
  deletepreview bullet, the
  `preview_chat_delete_impact` import after the
  deletepreview import, and the `__all__` entry after
  `preview_delete_impact` - disjoint blocks from
  P-148's bullet-after-bindingcensus and
  exports-after-census_bindings.
- `tests/test_p149_chat_delete_impact.py` (new) - the
  battery (see Counts).
- One entry appended to
  docs/CLEAN_ROOM_LOG_2026-10-30.md. README.md never
  touched. CAMPAIGN_STATE.md / CURRENT_STATE.md
  untouched (the keeper's banking work).

## Honest limitations

- The preview judges the world as it stands at read
  time: a chat deleted, bound or unbound after the
  preview changes the outcome, and delete_chat
  re-decides nothing scenario-side when it runs - it
  simply never touches the binding store, which is
  the fact this preview exists to name beforehand.
- The cascade question remains OPEN and is named as
  Volmarr's to take: this slice deliberately changes
  no write behaviour, so orphaned bindings will keep
  accumulating on chat deletion until either owners
  unbind them per chat (the standing road, aimed by
  P-148's census and by this preview) or the cascade
  decision is taken expressly.
- Only scenario custody is judged. A chat's other
  deletion custodies (checkpoints, databank, undo,
  vision links, attachments, folder-watch
  registrations) are the chats subsystem's own law
  and are not read here; nor are the chat's P-093
  variables, which live under that store's own law.
- The P-148 union was NOT verified in this worktree
  (it cannot be: P-148 is absent from this base by
  design) - it is verified by the keeper at banking
  with the combined batteries and the forge
  confirmation suite. This slice's no-regression claim
  rests on its own full suite's zero failures plus the
  neighbour fence on this base.
- There is no playback in this slice, and none is
  claimed (P-027 law: content is data, never code).

## Counts

- Battery: tests/test_p149_chat_delete_impact.py -
  see hidden_files/P149_EVIDENCE.md for the counted
  runs (battery, neighbour fence, full suite), read
  from the log files.
- Migration: NONE (head stays 0041, battery-pinned).

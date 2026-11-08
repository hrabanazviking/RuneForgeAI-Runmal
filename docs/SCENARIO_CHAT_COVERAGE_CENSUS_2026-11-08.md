# P-152 - Chat Coverage Census (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-131..
P-151 precedents. The derivation rests on Runmal's own
in-tree record only (full weighing in the team's
scout/design record, hidden_files/P152_SCOUT.md and
P152_DESIGN.md).

Base: b5a8738 (P-151 banking record; P-001..P-151
banked). P-150 (binding custody census, team-02) and
P-151 (library definition census, team-03) are IN this
base; this slice neither duplicates nor touches their
ground (P-150's road is a bindings census literal,
P-151's a library literal; this slice's road is a chats
literal appended at the router's end, and its __init__
entries sit after the chatcensus entries, the one
anchor the scout named - pure additive insertions the
keeper reconciles at banking exactly as P-148..P-151
were). Migration: NONE - head stays 0041. No
storage-shape change, no new store, and no
write-behaviour change anywhere.

## The weighing

- **Chat coverage census - taken.** Every census in
  the part rows bindings (P-144, P-148, P-150),
  definitions (P-151) or report rows (P-145). The
  binding censuses build their rows from
  list_bindings, so a chat with no binding appears in
  NO census at all, and no road answers the chat-side
  library question - which of an owner's chats carry
  a binding at all, which stand sound, which carry a
  drifted pin, which carry a binding whose definition
  is gone - except walking every chat by hand through
  the P-132 per-chat binding read, judging the
  definition-axis verdict by eye against the
  definition list: exactly the by-hand gap P-144's
  own derivation named as its justification,
  transposed to the chat axis, and the exact mirror
  of the gap P-151 closed for definitions ("a
  definition with no bindings appears in no census at
  all"). The consumers are standing roads, not
  invented ones: bind aims at one chat (an owner
  choosing a chat to bind needs a FREE chat - bind
  refuses an already-bound one, P-132), unbind aims
  per chat, the P-149 delete-impact preview aims per
  chat, and chat deletion itself is per chat. Every
  one of those acts is aimed from the chat side, and
  the chat side had no census to aim from. This slice
  is that census: P-144's verdicts joined per chat
  over the caller's full chat list, so unbound chats
  row as unbound and orphaned bindings are counted
  honestly in the totals while rowing under no chat -
  P-151's stale-in-totals law, transposed.
- **Wiring delete_chat to cascade the binding record -
  NOT taken, argued plainly.** The record has not
  moved towards it: P-149 weighed it at full length
  and reserved it expressly ("the decision is
  Volmarr's expressly" - its banking record states it
  stands open for Volmarr's word), P-150 declined it
  again, and P-151 declined it again ("overriding two
  fresh, deliberate in-tree reservations with no new
  evidence" - now three). This scout found no new
  evidence. It stands open deliberately. This census
  changes no write behaviour; if anything it sharpens
  the naming the decision will be taken on (P-148 /
  P-149 / P-150 / P-151 already name every orphan it
  would remove, and this slice names them from the
  chat side too).
- **Organisation orphan census - declined, standing,
  evidence re-weighed and UNCHANGED:** orphan rows
  are filtered at every read (P-134), P-139 names the
  row per definition before a delete, and the P-151
  asymmetry still decides it - an orphaned binding
  can be removed by the standing unbind road once
  named, while NO road removes an orphan organisation
  row, so a global orphan list names what no consumer
  can act on. Censuses name, never repair.
- **Organisation-inclusive chat/definition census -
  declined for this slice,** same ground as P-151's
  carve-out: P-134's roads already answer organisation
  per definition and per tag; folding a filing read
  into a coverage census would blur both. The taken
  scope is binding coverage.
- **Within-library duplicate-content census -
  declined, standing** (P-145 / P-147 / P-150 /
  P-151): identity-by-checksum is P-141 / P-143 pack
  law; P-137 clones are honest citizens.
- **Portable-archive inclusion of the scenario
  stores - declined for this slice, standing:** a
  portable-subsystem line item, named open there in
  every weighing; a write-format change across three
  stores, not a scenarios read surface.
- **Binding / definition history retention -
  declined, standing:** no named consumer; a
  storage-shape change.
- **Candidate create preview, unbind-impact preview,
  duplication preview, stored / pack export previews,
  rebind preview, collections / folders, general
  library status aggregate - declined, standing
  grounds unchanged** (P-142 / P-145 / P-148 / P-150 /
  P-151 weighings; the aggregate in particular would
  restate banked envelopes, where this census
  surfaces rows no envelope contains - the unbound
  chats).
- **Per-chat delete-impact for ALL chats (a
  P-149-shaped census) - declined:** P-149 already
  answers per named chat before the act, and its
  impact counts are read from the one binding record;
  a bulk form would restate this census's rows plus
  P-149's per-chat envelope. The coverage census is
  the missing roster; the preview stays per chat by
  design.
- **Playback / runtime / condition evaluation /
  scripting EXECUTION - declined ABSOLUTELY** (P-027
  law: stored content is data, never code).

## The contract

- `src/runmal/scenarios/chatcoverage.py` (new) - the
  async read service. `census_chat_coverage(session,
  bindings, owner_id, definitions)` composes the one
  owning verdict service over the caller's own
  inputs: `census_bindings` (P-144), whose rows are
  queued per chat_id in row order (the P-150 / P-151
  duplicate-id law: a hand-damaged store holding two
  rows for one chat joins the first to the chat; the
  surplus is counted, never hidden). Chats are the
  caller's own, read owner-scoped from the Chat table
  in the chats service's own list order
  (Chat.created_at, then Chat.id for determinism).
- Coverage law (exactly one state per chat) - no
  third state law is invented; each bound row carries
  P-144's row verbatim, and the coverage state is its
  plain reading on the chat axis: `unbound` (no
  binding row names this chat), `sound` (the carried
  binding is current), `definition_drift` (superseded
  or ahead), `definition_gone` (stale - the definition
  is gone, split out from drift because on a standing
  chat the distinction is the actionable one: a
  drifted pin can be refreshed by unbind + bind
  against a living definition, a gone definition
  leaves nothing to rebind to; P-151's own law
  likewise counts stale apart from drift). The chat
  axis needs no verdict: a rowed chat exists for this
  owner by construction. `CHAT_COVERAGE_STATES` names
  the four in law order.
- Rows: one per chat in the caller's list, carrying
  identity facts only - `chat_id`, `title`, `is_group`
  (Chat.group_id is not None - the group flag P-138
  reads), `created_at` (the Chat row's own stamp,
  ISO) - plus `binding` (the P-144 census row
  verbatim, or None) and `coverage_state`. No
  messages, no character facts, no seeded content
  (binding summaries never carry it, P-135).
- Counts, every one summed from the rows and verdict
  rows themselves: chats_total and the four per-state
  chat counts; bindings_total (every P-144 row for
  the caller); bindings_rowed (rows joined to a
  standing chat); bindings_orphaned_chat (verdict rows
  whose chat is not among the caller's chats -
  deleted, never existed, or another owner's; the
  three answer alike, P-148's law);
  bindings_surplus_rows (verdict rows for a standing
  chat beyond the first - hand-damage only, bind
  forbids them); definitions_referenced (DISTINCT
  definition ids among rowed bindings).
  Reconciliation identities: the four chat-state
  counts sum to chats_total; rowed + orphaned +
  surplus sums to bindings_total. Bindings are
  counted per row and chats per chat, stated
  separately exactly as P-148 states its distinct law.
- Five standing honesty notes in fixed order (pure
  read; naming is not repair - a bound chat stays
  bound until unbound per chat, an unbound chat stays
  unbound until bound, and the census aims the
  standing bind / unbind roads while being neither;
  the subject is the chat; the join adds no third
  fact and carries no seeded content; chat facts are
  identity facts only, owner-scoped, truth-as-data).
- One additive road: `GET /scenarios/chats/census`,
  appended at the end of scenarios/router.py after
  the P-147 handler, under its own section comment -
  disjoint hunk ground from P-150's bindings-block
  road and P-151's library-block road. The handler
  passes `_bindings()` and
  `_store().list_for_owner(user_id)` (the P-144 road's
  own inputs). No 404 case: an owner with no chats
  answers the honest zero census, and an owner with
  chats but no bindings answers every chat unbound.
  Declaration-order safety: the road is two segments;
  no existing two-segment GET road has a variable
  second segment, so "chats" / "census" can be
  captured by no {definition_id} road and captures
  none (battery-pinned).
- `src/runmal/scenarios/__init__.py` (additive) - a
  subsystem-map bullet after the chatcensus bullet,
  the `CHAT_COVERAGE_STATES` / `census_chat_coverage`
  import after the chatcensus import, and the
  `__all__` entries after `census_binding_chats` -
  the one anchor shared with P-150's __init__ delta,
  banked in this base; pure additive insertion.
- `tests/test_p152_chat_coverage_census.py` (new) -
  the battery (see Counts).
- One entry appended to
  docs/CLEAN_ROOM_LOG_2026-10-30.md. README.md never
  touched. CAMPAIGN_STATE.md / CURRENT_STATE.md
  untouched (the keeper's banking work).

## Honest limitations

- The census is a pure read and judges coverage only;
  it changes no write behaviour. The delete_chat
  cascade remains OPEN and deliberately untaken:
  P-149 reserved the decision expressly for Volmarr
  and P-150 / P-151 declined it again; this slice
  records the same position with the full argument
  above, rather than overriding three fresh in-tree
  reservations.
- The coverage state reads the chat's FIRST binding
  row in binding order; a hand-damaged store holding
  a second row for the same chat is named by
  bindings_surplus_rows in the totals, and the
  per-binding truth stays on the P-144 / P-148 /
  P-150 censuses, untouched beside it.
- The join claims nothing P-144 does not claim:
  organisation filing, report content, message
  content and seeded content are absent here by
  construction, not by omission. Chat facts are
  identity facts only.
- A group room rows here exactly as any standing chat:
  custody judges existence, not bindability (bind's
  refusal law is bind's, P-148's precedent).
- No pre-slice full-suite run was taken in this
  worktree; the no-regression claim rests on the
  post-slice full suite's zero failures plus the
  neighbour fence, reconciling exactly with the
  banked counts.
- There is no playback in this slice, and none is
  claimed (P-027 law: content is data, never code).

## Counts

- Battery: tests/test_p152_chat_coverage_census.py -
  see hidden_files/P152_EVIDENCE.md for the counted
  runs (battery, neighbour fence, full suite), read
  from the log files.
- Migration: NONE (head stays 0041, battery-pinned).

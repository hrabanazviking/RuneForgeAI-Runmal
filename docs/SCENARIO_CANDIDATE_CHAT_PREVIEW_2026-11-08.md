# P-147 - Chat-Scoped Candidate Bind Preview (Part IX, DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part IX only its part-table
line - "IX | Scenarios - the Visual Novel Engine |
P-131 - P-154" - and no per-slice entries. This slice's
scope is therefore DERIVED, not roadmap-verbatim, stated
plainly as derived everywhere, following the P-101 /
P-117 / P-131..P-146 precedents. The derivation rests on
Runmal's own in-tree record only (full weighing in the
team's scout/design record, hidden_files/P147_SCOUT.md
and P147_DESIGN.md).

Base: 0de6465 (P-145 banking record; P-001..P-145
banked). P-146 (candidate replace preview, team-01) is
banking concurrently ahead of this slice and is NOT in
this base; its module, battery and slice doc were read
read-only in the team-01 worktree so this slice neither
duplicates nor collides with it: P-146 adds
candidatepreview.py and POST
/scenarios/{definition_id}/replace-preview (a candidate
judged pre-store, definition-side), while this slice
adds candidatechatpreview.py and POST
/scenarios/{definition_id}/replace-preview/{chat_id}
(the same candidate judged against one chat). The
router.py, scenarios/__init__.py and clean-room edits
are additive in disjoint blocks, and the keeper
reconciles the union at banking (P-146 before P-147).
Migration: NONE - head stays 0041. No storage-shape
changes and no new store: the preview parses a
candidate body in memory and reads the definition and
binding stores and the chat's P-093 variables; it
stores nothing.

## The weighing

- **Chat-scoped candidate bind preview - taken.** The
  Part IX preview matrix had exactly one empty cell.
  Stored body, definition-side: P-136's bind-plan.
  Stored body against one chat: P-138's chat-scoped
  preview. Candidate body, definition-side: P-146's
  replace-preview. Candidate body against one chat:
  nothing. P-146's own third standing note bounds its
  candidate plans exactly as P-136's notes bounded its
  stored plan - "both plans are definition-side only:
  no chat has been consulted and bind-time refusals are
  not judged here; the plans name seedable keys, not
  landed keys" - and P-136's identical bounds were
  answered by P-138 for the stored body. P-146's scout
  declined this composition for its slice on one
  ground: no in-tree record naming a consumer, with
  the definition-side candidate plan plus P-138 after
  a real replace covering the need in two named steps.
  That ground does not hold as a standing decline, for
  the reason P-140 and P-146 themselves pin: a
  successful replace is permanent for the current body
  - the stored definition and its import report are
  overwritten, there is no un-replace and no definition
  history - so the two-step cover requires committing
  the irreversible act FIRST and only then learning,
  via P-138, what the new body would seed or skip in a
  specific chat and whether that chat would refuse the
  bind at all. The preview family's whole purpose is
  inspect-before-commit (P-136 for bind, P-138 for
  bind-against-a-chat, P-139 for delete, P-140 for
  replace's impact, P-143 for pack import, P-146 for
  replace's candidate); the candidate x chat verdict
  is the one ordering that purpose cannot reach today.
  Every ingredient already exists as an owning slice's
  own verb: the store door's parser as P-146 applies
  it, P-132's pure plan_materialisation, bind's
  blocker facts and P-093's presence law as P-138
  calls them. This slice is the join, as a pure read:
  PUT remains the only replacer and POST bind the
  only binder.
- **Library duplicate-content census - declined.**
  P-145 weighed it and found it weaker: identity by
  checksum is P-141/P-143's pack law, judged there
  against packs; no in-tree record names within-
  library duplicate groups as a missing fact, and
  P-137 clones are honest citizens by design, not
  drift. P-146 additionally declined a third census
  deliberately. No new naming has appeared since.
- **Unbind-impact preview - declined.** Standing
  evidence since P-141, unchanged: the unbind road
  already answers its one fact with every unbind (the
  record goes, seeded content stays - P-132); a
  preview would restate it and add no knowledge.
- **Duplication preview - declined.** Standing
  evidence (P-144): duplication is non-destructive, it
  creates a fresh citizen, orphans nothing and
  supersedes nothing; no record names a risk needing
  inspection before it.
- **Organisation orphan census / cleanup - declined.**
  Standing law: orphan organisation rows are filtered
  at every read (P-134) and P-139 names the row per
  definition before deletion; censuses name, never
  repair, and cross-store cleanup remains declined
  (independent stores). This slice performs no
  cleanup and adds no cascade.
- **Stored-export / pack-export previews - declined.**
  P-145's ground: both exports are pure reads whose
  own envelopes already carry their honest reports
  (P-133 not_restored, P-141 manifest); a preview of
  a read adds no knowledge.
- **Bind-plan vs actual-bind reconciliation -
  declined.** Standing evidence: the binding record
  already IS the account of what landed, and the
  retrospective comparison is exact only while the
  definition's current revision still equals the
  pinned one - after a replace it is gone (history
  retention, declined). This slice is prospective:
  it judges a body that is not stored yet against a
  chat as it stands, which is the opposite direction.
- **Definition history retention - declined.**
  Standing declination, evidence unchanged: no
  in-tree record names a consumer, and retention
  would be a storage-shape change. The candidate
  previews meet the underlying need honestly - judge
  before committing - while retaining nothing.
- **Portable-archive inclusion of the scenario
  stores - declined for this slice.** The archive is
  a SQL-row bundle; the scenario stores are data-dir
  JSON documents by P-131 design - a portable-
  subsystem slice, named open for that line.
- **Collections / folders - declined.** P-134's
  honest bound ("No collections or folders"); no
  named need.
- **Playback / runtime / condition evaluation -
  declined. Executing stored scripting - declined
  ABSOLUTELY.** P-027 law: content is data, never
  code. The candidate is parsed and planned as data;
  nothing it carries is evaluated or run.

## What landed

- `src/runmal/scenarios/candidatechatpreview.py`
  (new) - the chat-scoped candidate preview service.
  `preview_candidate_for_chat(session, record,
  user_id, chat_id, body, *, bindings=None,
  variables_base_dir=None)` is async in P-138's shape.
  The chat's existence is decided BEFORE the candidate
  is judged: the Chat row is read owner-scoped exactly
  as chatpreview reads it, and an unknown or foreign
  chat returns None - even with a malformed candidate -
  so existence never leaks on either side. On an owned
  chat the candidate is judged through the store door
  exactly as P-146 applies it (a non-object body raises
  ScenarioStoreError; otherwise P-026's
  parse_scenario_file alone, raising ScenarioParseError
  on refusal, before any envelope exists - P-146 is
  not in this base, so the three-line door is stated in
  the module in full, as P-146 itself re-stated
  store.py's private law; no second validation law is
  invented). The envelope: the P-136 identity four for
  the STORED record (id, name, current revision, source
  format), next_revision (current + 1, P-131's replace
  law) and chat_id; the candidate block (parsed name
  and source format, the would-be native shape -
  export_native of the parse - and its import report,
  P-131-law counts, P-132's plan over the would-be
  shape, and P-136 plan counts); the current body's
  plan counts; bind's blockers as data in bind's
  decision order (group room, already bound - naming
  the standing binding - and non-empty, with its
  message count), read through the same facts bind
  reads; would_bind (no blockers) for the candidate as
  if stored at next_revision; the candidate plan's
  seedable keys split by P-093's own presence law
  (resolve_key + get_entry under the scenario writer,
  flags then variables, bind's own already-present
  reason) in `keys`, the STORED plan's split by the
  same law in `current_keys`, and `key_deltas` - the
  sorted full-key added / removed lists for both
  halves of the split, read from the two splits
  themselves so they cannot drift; and six standing
  honesty notes in fixed order (pure read; the store
  door; the as-if-stored bound, naming P-138's road as
  the current revision's own chat verdict; the chat as
  it stands, re-decided by bind; the P-093 presence
  law; truth-as-data with the unmappable naming).
  Pure read: the candidate is stored nowhere, nothing
  is bound or seeded, and every store document is
  byte-untouched (battery-pinned).
- `src/runmal/scenarios/router.py` (additive) - one
  road: POST
  /scenarios/{definition_id}/replace-preview/{chat_id}
  answering 200 with the envelope, declared in its own
  P-147 section after the sharing-pack section at the
  file tail. The definition is fetched owner-scoped
  first (unknown or foreign answers 404 "scenario
  definition not found", even with a malformed
  candidate); the service's None answers 404 "chat not
  found" (unknown and foreign alike, even with a
  malformed candidate - the chat is decided before
  the body, mirroring P-131's existence-before-body
  law); a refused candidate on an owned definition
  and owned chat answers 422 (ScenarioParseError /
  ScenarioStoreError, the create/replace roads' own
  mapping) and changes nothing. The segment pair
  replace-preview + {chat_id} shares no road with
  P-146's replace-preview (different segment count),
  P-138's bind-plan/{chat_id} (different literal) or
  P-132's bindings/{chat_id} (different block).
- `src/runmal/scenarios/__init__.py` (additive) - the
  preview_candidate_for_chat name exported in the
  house style, plus one subsystem-map bullet.
- `tests/test_p147_candidate_chat_preview.py` - the
  battery (15 tests; see Evidence).

## Honest bounds

- As-if-stored, never stored: would_bind and the
  splits judge the candidate as if a replace had
  landed it at next_revision and a bind followed.
  Neither act has happened; each re-decides every
  fact when it runs - a chat that changes, a library
  that changes, or a different body actually replaced
  all change the outcome. The preview is a statement
  about the candidate and the chat as they stand when
  read, never a promise about replace or bind time.
- Binding today binds the CURRENT revision: an owner
  who binds without replacing gets P-138's verdict,
  not this one; this envelope names the current
  revision and next_revision precisely so the two are
  never confused.
- The candidate's unmappable raw values are not part
  of its native shape and would not persist (P-131);
  the candidate report carried here names every one.
- The preview performs no replace, no bind, no
  cleanup and no cascade, and no banked answer
  changes: P-146's definition-side envelope, P-138's
  chat-scoped envelope and every other Part IX surface
  keep their exact standing shapes beside the new
  road (at banking the keeper unions P-146 first;
  this slice's base honestly lacks P-146's road, and
  the battery says so rather than asserting over it).
- There is no playback in this slice, and none is
  claimed.

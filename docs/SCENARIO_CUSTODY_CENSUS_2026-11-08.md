# P-150 - Binding Custody Census: Both Axes Joined (Part IX, DERIVED scope)

Part IX slice. The roadmap gives Part IX only its part-table
line ("Scenarios - the Visual Novel Engine", P-131 - P-154);
no verbatim P-150 entry exists. This slice's scope is DERIVED
from Runmal's own in-tree record, as P-131..P-149 were, and is
stated as derived everywhere it is named.

## The weighing

- **Two-axis custody census - taken.** A binding answers to
  two parents, and by P-148 both axes had a judge -
  separately. P-144 censuses the definition axis (current,
  superseded, ahead, stale) and states in its own fifth note
  that it judges no chat liveness; P-148 censuses the chat
  axis (live, orphaned) and states in its own notes that the
  two axes are independent and a binding can be orphaned and
  stale at once. The joint state was named in-tree but judged
  nowhere: an owner asking which bindings are sound, which
  drift on one axis, and which are broken on both, had to
  fetch two censuses and merge them by hand, row by row,
  with no road accountable for the merge. This slice is that
  merge, built by composing the two owning services over the
  same P-135 rows - no third state law is invented, and every
  count is summed from the joined rows themselves.
- **Wiring delete_chat to cascade the binding record -
  declined for this slice.** P-148 named this the honest next
  question if the cascade is ever wanted, and it stands open
  deliberately. Three grounds: (a) the Part IX pattern is
  name first, judge after banking - P-149, the preview that
  names chat-delete impact, is concurrent (team-01), not yet
  banked, and is not in this base by design, so its naming
  has not landed to be judged from; (b) a cascade is a
  write-behaviour change inside the chats subsystem, not a
  scenario read surface; (c) the binding store's no-cascade
  law is deliberate on the definition side (P-132 / P-139),
  and no in-tree record has taken the behaviour decision for
  the chat side. The censuses name the orphans on both axes
  and the standing unbind road removes them per chat once
  named (battery-pinned end to end here, including a
  doubly-broken binding).
- **Organisation orphan census / cleanup - declined.**
  Standing law (P-144 / P-147 / P-148): orphan rows are
  filtered at every read (P-134), P-139 names the row per
  definition before deletion, censuses name and never
  repair, and cross-store cleanup remains declined.
  Evidence unchanged.
- **Within-library duplicate-content census - declined.**
  Standing (P-145 / P-147): identity-by-checksum is
  P-141 / P-143 pack law; P-137 clones are honest citizens
  by design, not drift. No new naming has appeared since.
- **Candidate create preview - declined.** Standing
  (P-148): create is neither permanent nor destructive and
  the stateless P-026 import road already dry-reads a body.
- **Unbind-impact preview - declined.** Standing ground
  since P-141: the unbind road already answers its one fact
  with every unbind (the record goes, seeded content stays).
- **Duplication preview - declined.** Standing (P-144):
  duplication is non-destructive, orphans nothing and
  supersedes nothing.
- **Stored-export / pack-export previews - declined.**
  Standing: a preview of a pure read adds no knowledge.
- **Rebind / refresh preview - declined.** Standing
  (P-148): bind's own law refuses the only chats it could
  target, so its would_bind is false by construction.
- **Definition history retention - declined.** Standing:
  no named consumer, and retention would be a
  storage-shape change.
- **Portable-archive inclusion of the scenario stores -
  declined for this slice.** A portable-subsystem line,
  named open there in every weighing.
- **Collections / folders - declined.** P-134's honest
  bound; no named need.
- **Playback / runtime / condition evaluation - declined.
  Executing stored scripting - declined ABSOLUTELY.**
  P-027 law: content is data, never code. This slice
  evaluates nothing and runs nothing.

## What landed

- `src/runmal/scenarios/custodycensus.py` (new) - the
  two-axis census service. `census_binding_custody(session,
  bindings, owner_id, definitions)` is async (the chat axis
  lives in the SQL Chat table, the P-148 precedent) and
  composes the two owning services over the caller's own
  inputs: `census_bindings` (P-144) for the definition axis
  and `census_binding_chats` (P-148, live id set built from
  the same definitions list exactly as its road builds it)
  for the chat axis. Joined rows are matched on the
  binding's own id, consumed in row order per id, so a
  hand-damaged store holding two rows that share an id
  still joins each chat verdict to one definition verdict
  in order. Each row is the P-144 census row verbatim,
  enriched with exactly `chat_exists` and `chat_state`
  (P-148 verbatim) and `custody_state` under a four-state
  law: `sound` (current + live), `definition_drift` (the
  definition axis broken - superseded, ahead or stale -
  beside a standing chat), `chat_orphaned` (a current pin
  whose chat is gone), `doubly_broken` (both axes broken
  at once). `CUSTODY_STATES` names the four in that order.
  Groups roll the rows up per definition in first-binding
  order (P-144's group shape plus the four custody counts),
  and the counts carry both parents' counts whole (the four
  definition states; live / orphaned; chats counted DISTINCT
  per P-148's law) beside the four custody counts - every
  count summed from the joined rows and groups themselves.
  Five standing honesty notes in fixed order (pure read;
  names never repairs on either axis; the join adds no third
  fact; owner-scoped existence; truth-as-data).
- One additive road: `GET /scenarios/bindings/custody-census`
  in `scenarios/router.py`, declared in the bindings block
  after the P-148 chat-census road and before the {chat_id}
  binding read so the literal is never read as a chat id.
  No 404 case: an owner with no bindings answers the honest
  zero census.
- `scenarios/__init__.py` (additive): the custodycensus
  subsystem-map bullet after the chatcensus bullet,
  `CUSTODY_STATES` / `census_binding_custody` exports.
- `tests/test_p150_custody_census.py` (new, 20 tests).
- This doc, and a clean-room log entry.

No migration (head stays 0041), no storage-shape change, no
new store, no write-behaviour change anywhere.

## Honest limitations

- The census is a pure read and judges custody only; it
  changes no write behaviour on either axis. Both cascades
  (definition delete, chat delete) remain deliberately
  untaken, and this slice does not soften that: it names
  doubly-broken bindings so the owner can aim the standing
  unbind road, which remains the only removal road.
- The join claims nothing neither parent census claims: a
  fact neither P-144 nor P-148 can state (seeded content,
  chat content, organisation filing) is absent here too,
  by construction, not by omission.
- The P-149 union was NOT verified in this worktree (it
  cannot be: P-149 is absent from this base by design). The
  keeper verifies it at banking - this slice's router and
  __init__ deltas sit in the bindings census block P-149
  does not touch (its preview road is chat-scoped), and
  the deltas are pure additive unions either way.

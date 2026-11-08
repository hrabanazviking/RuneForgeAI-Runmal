# P-111 - Voice Repeat-Acknowledgement Housekeeping (Part VII)

Derived scope, stated plainly: the governing roadmap
gives Part VII only its part line - "VII | Voice, the
Voxta Way | P-101 - P-116" - and no per-slice entries.
P-111 is DERIVED, not roadmap-verbatim, from in-tree
sources only: P-108's own recorded limitation, stated
in docs/VOICE_REPEAT_REQUESTS_2026-11-08.md section 4 -
"a deleted session's acknowledgements become inert
records - they name a session that no longer exists and
drive nothing" - with no road that ever removes one.
The keeper reviews this derived scope at banking.

Clean-room line: built entirely from Rúnmál's own
in-tree contracts - the P-108 acknowledgement store,
the P-101 session store as the live-set source, and the
voice JSON house pattern - with no outside source read
and no file downloaded (see the P-111 entry appended to
docs/CLEAN_ROOM_LOG_2026-10-30.md).

Base: 2e7864c (P-108 banking record). P-109 and P-110
bank before this slice in roadmap order and reconcile
at banking. Migration head: 0041. No migration taken.

## 1. The gap, exactly

P-108's AcknowledgementStore offers one-record
housekeeping only (clear), and only through a session
road - which answers 404 for a deleted session. So the
moment a session is deleted (its chat's sessions are
dropped), its acknowledgement records become
unreachable by every road in the app: no view shows
them, nothing can return them to pending, and nothing
can remove them. They accumulate install-wide for the
life of the install. P-108 recorded this plainly as a
limitation; P-111 is the housekeeping that closes it.

## 2. What landed

- src/runmal/voice/repeat_requests.py (extended) - the
  store learns to describe and prune itself:
  - AcknowledgementStore.session_ids() - the sorted
    session ids carrying at least one record.
  - AcknowledgementStore.record_count() - the total
    record count.
  - AcknowledgementStore.prune_orphans(live_ids) -
    removes every record naming a session that is not
    live; live sessions' records are never touched,
    in content or order; the store saves only when
    something was actually removed, so a no-op prune
    leaves the document byte-identical; returns the
    removed session ids (sorted) and record count.
  - housekeeping_view(store, live_ids) - the pure
    housekeeping truth: acknowledged sessions and
    records split into live and inert, with the inert
    session ids named, so a host sees exactly what a
    prune would remove before calling it.
  - prune_inert_acknowledgements(store, live_ids) -
    the prune plus a before/after report in one view.
- src/runmal/voice/repeat_router.py (extended) - two
  install-wide roads on the founding /api/v1/voice
  surface, bearer-gated like every API road:
  - GET /voice/repeat-requests/housekeeping - the
    housekeeping view. A pure read: it acknowledges
    nothing and deletes nothing.
  - POST /voice/repeat-requests/housekeeping/prune -
    removes inert records only; the report carries
    the before counts, the removed session ids and
    the after view. A prune with nothing inert
    removes nothing and says so.
- src/runmal/voice/router.py (one road extended) -
  DELETE /voice/chats/{chat_id}/sessions, the act
  that orphans a chat's sessions' acknowledgements,
  now prunes every acknowledgement whose session no
  longer exists in the same act and reports the count
  as repeat_acknowledgements_pruned (an additive key;
  chat_id and dropped are unchanged). The prune is
  deliberately global rather than scoped to the
  dropped chat: one housekeeping act clears all inert
  records, including any orphaned earlier by other
  paths, and the reported count is that act's total.
- Battery: tests/test_p111_voice_repeat_housekeeping.py
  (18 tests; see section 5).

## 3. Laws held

- Inert means exactly one thing: the record's session
  id is not in the session store. No age limit, count
  cap, or heuristic is invented - a live session's
  records are never pruned, however old they are.
- Housekeeping touches handling, never truth: pruning
  removes acknowledgement records only. P-105's
  detection is recomputed from evidence as always,
  and a live session's acknowledged requests stay
  acknowledged through any prune (pinned).
- A read deletes nothing: the housekeeping view - and
  a prune that finds nothing inert - leave the store
  document byte-identical (pinned at the file level).
- No migration, no new DB state, no new file: the
  same versioned JSON document, pruned in place.
- Signal-is-data law unchanged: no road in this slice
  creates a chat message, generates text, or calls a
  responder (pinned: chat messages identical before
  and after the whole housekeeping flow).

## 4. Honest limitations

- The housekeeping roads are install-wide, exactly
  like the acknowledgement store itself (the P-105
  lexicon / P-108 stance): any bearer-authenticated
  host can view the inert set and prune it. The view
  names inert session ids; that is the point of the
  surface, and it is stated plainly rather than
  dressed in per-owner wording the store cannot back.
- No periodic sweeper exists: inert records are
  removed when a host calls the prune road, or
  opportunistically when any chat's sessions are
  dropped. A session removed by direct store edits
  outside those roads leaves its records until the
  next prune.
- The character-asks half of VX-11 stays open on the
  P-102 responder seam, exactly where P-105 through
  P-108 left it. This slice is housekeeping; it
  fabricates no dialogue and moves no other open item.

## 5. Battery

tests/test_p111_voice_repeat_housekeeping.py - 18 tests:
the pure views (empty store, the live/inert split with
inert ids named and sorted, session ids + record count,
the view proven to be a pure read at the file level),
the prune (inert only, live records verbatim incl. note
and stamp, persistence round-trip, no-op byte-identity
incl. no file created for an absent store, the
before/after report, idempotence, any-iterable live
ids, a live session's acknowledged state surviving a
prune end to end), the HTTP roads (the housekeeping
view across empty / live / mixed states, prune removing
inert only with the live signal untouched and a second
prune at zero, reads proven pure at the file level,
401 without the bearer on both roads, chat-drop pruning
its own chat's records while the surviving chat's stay,
drop with no acknowledgements reporting zero, a drop
clearing a pre-existing orphan with the act-total
count, and the no-chat-message pin), and the 0041
migration pin. Neighbour and full-suite counts are
recorded from the run logs in
hidden_files/P111_EVIDENCE.md, never estimated here.

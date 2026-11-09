# P-177 - Workspace Binding-History Census (Part XI, Workspaces - the Companion That Works)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XI only its part-table line -
"XI | Workspaces - the Companion That Works | P-169 - P-186" -
and no verbatim P-177 entry exists anywhere in it. This slice
scope is therefore DERIVED, not roadmap-verbatim, from Runmal
own in-tree record only (full survey:
hidden_files/P177_SCOUT.md; design: hidden_files/P177_DESIGN.md):

- P-173 banked the binding history (every ended binding kept
  as data, served as a list with four counts summed inline)
  and P-175 banked single-entry owner-hand deletion. No
  surface aggregates the history estate: nothing answers how
  one owner ended bindings distribute by cause, by the folders
  live states today, by whether their chats still exist, by
  folder sharing across endings, or by label presence.
- P-176 evidence (team-02, Workspace Folder Tree, commit
  895ee90, NOT in this base) carried this cell forward in so
  many words: "History census over P-173 (first post-P-175
  slice)". In this base P-175 IS banked, so the sequencing
  condition is met honestly.
- The house pattern is the census (P-148 / P-164 / P-165 /
  P-171 / P-174): a pure read composing the owning surface
  verbatim, classified under a closed law, counts summed from
  the composed document own fields. P-165, the owner-wide
  face HISTORY census, is the direct precedent.

Weighed and declined WITH REASONS (scout): binding label
update (a write needing a new store verb in bindings.py and
a PATCH road in router.py - neither purely additive, both in
P-175 footprint, and no in-tree record states its update law;
stays named open), content / filename search over the tree
(presupposes P-176, not in this base), automatic retention /
bulk clear-all (thresholds need Volmarr ruling per P-175
record; none exists in-tree), writes in bound folders
(VX-57 fenced - the guard presupposes workspace tool calls
and none exist), execution / backends (VX-55/56, declined
ABSOLUTELY under P-027), watching (declined at P-169), and a
recursive census (P-176 owns navigation; a second scan).

Base: 152281159bf59f5294587472d4bc1f3185b7a47f (P-175 banking
record; banked P-001..P-175). Migration: NONE - head stays
0041, no 0042, battery-pinned. Disjoint from P-176: no
tree.py, tree_router.py, bindings.py, history.py,
history_router.py, listing.py, census.py, content.py,
router.py or folder_census files touched. Shared files with
P-176 at banking: app.py and workspaces/__init__.py
(additive hunks in disjoint regions) and the clean-room log
(append +1 entry) - flagged for keeper reconciliation.

## What lands

- `src/runmal/workspaces/history_census.py` (new) - the truth
  layer, composing `runmal.workspaces.history`
  `resolve_workspace_history` VERBATIM with no chat filter:
  * `build_history_census(history_document)` sums ONLY the
    P-173 document own fields and embeds it whole. Carried
    verbatim: `entry_count`, `unbound_count`,
    `chat_deleted_count`, `chat_count`. Folder-state axis:
    `folder_state_counts` plus `ready_count`, `missing_count`,
    `not_a_directory_count`, `unreadable_count` under P-169
    closed FOLDER_STATES law. Existence axis:
    `live_chat_entry_count`, `gone_chat_entry_count`,
    `live_chat_count`, `gone_chat_count` (distinct chats per
    side, from P-173 chat_exists judgements). Sharing axis:
    `distinct_folder_count`, `shared_folder_count`,
    `entries_on_shared_folders`. Label axis: `labelled_count`,
    `unlabelled_count` from the entries verbatim labels.
  * The closed `HISTORY_CENSUS_STATES` law: `no_history`,
    `no_live_chats`, `all_live_chats`, `some_live_chats`.
  * `resolve_workspace_history_census(session, store,
    user_id)` always returns a document, never None.
  * Six standing honesty notes (`HISTORY_CENSUS_NOTES`).
- `src/runmal/workspaces/history_census_router.py` (new) -
  GET /workspaces/history-census: the subject is the caller,
  no parameters, every state DATA at 200.
- `src/runmal/app.py` (additive wiring only) and
  `src/runmal/workspaces/__init__.py` (additive doc bullet).
- `tests/test_p177_workspace_history_census.py` (new,
  16 tests).
- This doc and the clean-room log (+1 entry).

## Honest limitations

(1) Folder states and chat existence are live read-time
judgements at the census call (P-173 law), never the state
at the ending. (2) The census is owner-wide only: the
per-chat filtered read stays P-173 road. (3) No retention,
bulk-clear, label-edit, search, write, execution or watching
surface lands here - each stays named open for its own
reason, above. Nothing was left unfixed: the two battery
failures in the first run were defects in this slice own
test expectations (a rebind-after-unbind count and an HTTP
owner-ordering assumption), fixed in the tests; the
implementation passed unchanged.

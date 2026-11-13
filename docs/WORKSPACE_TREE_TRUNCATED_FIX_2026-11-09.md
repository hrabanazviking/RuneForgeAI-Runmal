# P-179 - Workspace Tree Truncated at the Depth Cap (Part XI, FIX)

## Commission

A commissioned fix slice, not derived scope. P-178
(Workspace Filename Search, in flight on team-01 at
this slice's base and banking before it) discovered
the defect in banked P-176 and recorded it in its
evidence: P-176's workspace tree document does NOT
set `truncated` for a directory left unexpanded at
the depth cap, though P-176's own notes and slice doc
claim `truncated` names every partial tree, including
caps. The tree road therefore dressed a capped partial
tree as whole. P-178 compensated inside its own search
composition only; the tree road itself stayed wrong.
This slice fixes the tree road at its source.

Base: 0e8b9c3f5063ecdb3aafb0e4b6c72349f0d3a852
(P-177 banking record; banked P-001..P-177, PART XI
OPEN). Migration: NONE - head stays 0041.

## The defect, reproduced first

In `build_tree`'s `fill()`, the depth-cap return
(`if level >= max_depth: return`) left the capped
level's directory children `expanded False` /
`children None` and set nothing: `truncated` was set
only by the node cap and by a composed level's own
P-170 truncation flag, never by the depth cap.
Reproduced before any code change, two ways
(hidden_files/P179_REPRO.log, P179_PREFIX_BATTERY.log):

- a stubbed pure `build_tree` at max_depth 1 and 2
  over a nested listing returned an unexpanded
  directory with `truncated` False at both caps;
- the P-179 battery, run against the unfixed tree,
  failed exactly its five `truncated`-at-the-cap
  pins (5 failed, 4 passed - the honest-False pins
  already held).

## What landed

- `src/runmal/workspaces/tree.py` - ONE hunk, in
  `fill()` at the existing depth-cap return, and
  nowhere else: if any of the capped level's
  just-composed children is a directory (P-170's
  `KIND_DIRECTORY` law, verbatim), `truncated` is
  set before returning. The flag is read from the
  composed children themselves - P-178's
  document-side rule, applied at the source instead
  of in one consumer. No depth law, entry law or
  path law changed; no redesign; the module's
  notes already stated the true law and needed no
  mending - the code now keeps their promise.
  Files and symlinks at the cap are leaves and
  never make a tree partial; an empty or file-only
  cap level stays `truncated` False; a non-ready
  root never reaches `fill()` and stays False.
- `tests/test_p179_workspace_tree_truncated.py`
  (new, fresh-authored, P-005 discipline) - 9 tests:
  the cap at the root level, the nested cap, a pure
  `build_tree` pin (stubbed child listing, the
  P-176 unit-test precedent), an uncapped tree
  staying False, a file-only cap level staying
  False (with its depth-1 twin pinned True), a
  symlink at the cap staying False, an empty root
  at depth 1 staying False, a missing folder NOT
  being a depth cap (P-176's expectation preserved),
  and the HTTP road carrying the flag both ways.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## P-176 battery audit (the accomplice question)

P-176's battery was grepped for every `truncated`
assertion before the fix: it asserts False only for
the empty folder and the missing folder - neither
is a depth cap, and both stay False under this fix
(both batteries green together, 26 passed). NO
P-176 expectation encodes the defect, so none was
corrected: the defect's accomplice was an absence -
P-176's depth tests assert `expanded` / `children`
/ `node_count` on capped trees but never asserted
`truncated` there. This slice's battery is that
missing assertion, at full strength.

## P-178 composition, re-checked from its evidence

P-178's `build_search` sets its own `truncated`
from the tree flag OR any unexpanded directory node
in the composed document OR its match cap. Against
the fixed tree the depth-cap case already arrives
True from the tree, so P-178's compensation is a
correct no-op for depth caps; it still adds its own
value for refused expansions, which the tree names
by `expand_refused` instead - unchanged, and out of
this slice's commissioned scope. (P-178 is not in
this base; this is reasoned from its banked evidence
text and its source read in the team-01 tree.)

## Honest limitations

1. `truncated` at the depth cap names partiality,
   not size: a directory at the cap might in fact
   be empty - the tree did not look, so it does
   not claim wholeness. That is the honest side
   of the line, and P-176's stated law.
2. Refused expansions keep their own truth
   (`expand_refused` on the node) and do not by
   themselves set the tree's `truncated`; consumers
   needing search-style coverage semantics apply
   P-178's rule, as P-178 does.
3. Nothing else about the tree changed: same caps,
   same composition, same notes, same road.

## Carried forward, named open

- P-178 banks before this slice (roadmap order);
  the keeper reconciles and banks P-179 after it.
- Content search over the tree stays named open
  (P-178's decline: a new partial-read honesty law).
- Writes under a VX-57-style guard and execution
  VX-55/56 (P-027 absolute) stay fenced.

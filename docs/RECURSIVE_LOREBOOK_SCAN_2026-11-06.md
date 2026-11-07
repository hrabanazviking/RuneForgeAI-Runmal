# Recursive lorebook scanning (P-031) — 2026-11-06

Roadmap line: *Recursive scanning: entries triggering entries, with depth limits and cycle safety, token budget enforced.*

Part III (Lorebook Depth) opener. The slice is opt-in end to end:
every pre-P-031 call path behaves exactly as before, and recursion
happens only where a caller asks for it.

## What was built

- `src/runmal/lorebooks/scan.py` — the recursive scanner.
  - `ScanEntry` gains `content` (default `""`), carried by
    `from_orm`; `ScanHit` gains `depth` (default 0) and
    `triggered_by` (default None), so plain-scan hits are
    unchanged in shape and value.
  - `scan_entries_recursive(entries, messages, scan_depth, *,
    max_recursion_depth=MAX_RECURSIVE_SCAN_DEPTH, token_budget=None)`
    returns a `RecursiveScanResult` (`hits`, `tokens_used`,
    `budget_exhausted`, `depth_reached`). Round 0 is exactly
    `scan_entries` over the messages; each later round scans the
    content of the entries admitted in the previous round as if it
    were a fresh message (breadth-first, deterministic: within a
    round, candidates are considered in input/priority order).
  - Cycle safety is one global seen set across all rounds: an
    entry fires at most once per call no matter how many parents
    (or cycles) reference it, so mutually recursive entries
    terminate. `MAX_RECURSIVE_SCAN_DEPTH` is 5 (mirroring
    activation's `MAX_RECURSION_DEPTH`); a larger request is
    clamped to the cap, never honoured past it.
  - Token budget: round-0 (direct) hits are always admitted and
    their content cost is counted in `tokens_used`; the budget
    bounds *expansion* — a recursive candidate that does not fit
    the remaining budget is skipped (and never scanned later)
    while smaller later candidates may still be admitted, and once
    admitted content meets or exceeds the budget no further rounds
    run. `budget_exhausted` reports that the budget stopped, or
    would stop, expansion. Argument validation is strict
    (`max_recursion_depth` an int >= 0, bools rejected;
    `token_budget` None or an int >= 1).
- `src/runmal/lorebooks/activation.py` — `activate()` gains
  keyword-only `recursive_hit_ids` / `hit_depths`. A plain key
  firing for a recursive hit is relabelled `via="recursive"` and
  reported at its discovery depth; the depth is consulted only
  for entries actually relabelled, so delay/sticky/constant
  firings always report depth 0. Absent/None (and empty)
  arguments are inert: pre-P-031 behaviour is unchanged, which
  the battery pins.
- `src/runmal/lorebooks/preview.py` — `preview_activation()` gains
  keyword-only `recursive_scan=False` / `max_recursion_depth`.
  With `recursive_scan=True` the preview discovers entries
  through recursive scanning and the result gains exactly four
  keys: `recursive_scan`, `max_recursion_depth`,
  `recursion_depth_reached`, `recursion_budget_exhausted`. The
  default path is byte-identical to before, and both live callers
  (the lorebook router and the prompt inspector) stay on it.
- Two-phase budget, stated plainly: one budget, enforced twice
  for two different jobs. The scanner's budget is a *discovery
  guard* bounding how far recursion explores; the unchanged S204
  budget/priority pass alone decides final inclusion, and the
  preview's `tokens_used` is S204's number only.
  `recursion_budget_exhausted` is a discovery signal, not a
  discard reason.
- Defects found in the inherited (uncommitted) implementation
  and fixed inside this slice:
  - `budget_exhausted` stayed False when round-0 content alone
    met/exceeded the budget and no expansion round ran (notably
    at `max_recursion_depth=0`); the flag is now computed before
    the early return and the contract is documented.
  - The activation depth override applied to *any* firing whose
    id was listed as recursive (an armed-delay firing could
    report `via="delay", depth=3`); depth is now gated on the
    recursive relabel itself.
  - `max_recursion_depth` above the documented hard cap was
    silently honoured; it is clamped to
    `MAX_RECURSIVE_SCAN_DEPTH`.
  - A generator (or any one-shot iterable) of entries was
    silently exhausted by the id-index pass and scanned as
    empty; entries are materialised once at entry.
  - Duplicate entry-id rows could each produce a round-0 hit,
    breaking the fires-at-most-once guarantee; round 0 now
    skips ids already seen (the first row supplies the content
    and cost, as the id index already did).

## Test maintenance

- No existing test was changed and no assertion was weakened.
  No migration: the schema head stays 0023, and no stored shape
  changes (recursion is runtime behaviour over existing rows).
- New battery: `tests/test_p031_recursive_scanning.py`
  (50 tests, all passing; output in
  `hidden_files/p031_battery.log`).

## Not in this slice

- No router/API exposure: the preview endpoint and the prompt
  inspector still call the default path, so recursive scanning
  is reachable today through the preview function only. Wiring
  a caller-facing toggle is a later slice's call.
- Gate finding F1 (a native lorebook carrying `at_depth`
  entries cannot enter the DB store) is untouched — that is
  expressly P-038's road.
- No persistence: recursive provenance (`depth`,
  `triggered_by`) lives in the scan/activation results of one
  tick and in the preview dict; nothing is stored per chat.
- No change to `{{lore:...}}` reference expansion (S203's
  separate, name-based recursion), which composes with, but is
  not replaced by, keyword recursive scanning.

## Clean-room basis

Built from Rúnmál's own roadmap line, its own S202/S203/S204
lorebook pipeline, and the public world-info behaviour already
recorded in P-002's census. No SillyTavern or Voxta source was
inspected; the slice's test fixtures are authored fresh in the
test module (P-005 discipline).

## Carried limitations (honest record)

- Delay provenance loss: a recursive hit on a delay-configured
  entry only arms the delay; when the entry later fires it
  reports `via="delay", depth=0`, because `EntryState` carries
  no pending via/depth across ticks. A recursive hit landing
  during cooldown is suppressed like any key hit.
- Round-0 budget exemption: direct hits are admitted and
  counted even when they alone exceed the budget, so scanner
  `tokens_used` may exceed `token_budget`; the S204 pass is
  the enforcement that bounds the actual prompt. Callers must
  not assume `tokens_used <= token_budget` from the scanner.
- Discovery is scan-based, not activation-based: in preview, a
  delay-armed (or budget-doomed) parent's content still
  discovers recursive children, and a constant entry's content
  is never scanned at all (constants are not scan hits), so a
  constant entry cannot be a recursion parent.
- Budget-skipped subtrees are pruned: a candidate skipped for
  cost is marked seen before the budget check, so entries
  reachable only through it are never discovered this call.
  (No admission is lost thereby: remaining budget only shrinks,
  so a candidate that does not fit now can never fit later.)
- Secondary-key narrowing: in a recursive round an entry's
  primary AND secondary keys must co-occur in the single parent
  content that triggers it; round 0 may satisfy them from
  different messages inside the scan window. The narrowing is
  what keeps `triggered_by` attribution to one parent honest.
- The shared token estimator charges `max(1, len // 4)`, so an
  admitted entry with empty content costs 1 token of scan
  budget. This matches S204's accounting exactly and is kept
  for consistency between the two phases.
- Two-phase signals do not reconcile by design:
  `recursion_budget_exhausted=True` with every row included is
  possible, as is a recursive row discarded by S204 with the
  flag False.

## Evidence

- Battery: 50 passed / 0 failed
  (`hidden_files/p031_battery.log`).
- Neighbours (S201/S202/S203/S204/S209/S213/S214/S215 scan,
  activation, budget, editor, hardening, trace, e2e and
  inspector tests, S304, P-019, P-027): 134 passed / 0 failed
  (`hidden_files/p031_neighbours.log`).
- Full suite in the team-01 worktree: 1293 passed / 4 skipped /
  0 failed (`hidden_files/p031_fullsuite.log`) — exactly the
  P-030 merged tree's 1243 passed / 4 skipped plus this
  battery's 50.

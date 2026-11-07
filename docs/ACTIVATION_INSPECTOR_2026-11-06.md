# Activation inspector (P-043) — 2026-11-06

Roadmap line: *Activation inspector: "why did this entry fire" —
the matched keys and roll shown per message (Part XIII's
Inspector consumes this).*

## What was built

- src/runmal/lorebooks/inspector.py — the explanation layer
  over the existing engine. It invents no activation behaviour:
  the canonical outcome of a tick comes from
  preview_activation (the same pipeline the editor preview and
  the prompt inspector run), and every other fact is recomputed
  with the engine's own public cores — the P-037 windowed scan
  (matched keys, message and external indices, selective logic,
  recursion depth, triggered_by), the P-043 near-miss scan
  (primary matched, secondary gate refused), and the matcher's
  recorded scores. The output is DATA — one explanation dict
  per entry, a per-message breakdown, and tick totals — so
  Part XIII's Inspector (and any other consumer) renders it
  without re-deriving anything. Payload schema tag:
  runmal-p043-activation-inspection-v1.
  - Per entry, to the extent the engine's records carry each
    fact: the outcome (status in the preview vocabulary —
    included / discarded / not_triggered / group_excluded /
    disabled) plus a single deterministic reason code and a
    one-sentence summary built only from recorded facts.
  - Keys: every declared primary/secondary key, which matched
    and which did not, the P-032 selective logic, the
    secondary counts and the gate verdict, and WHERE the
    matches landed (message_indices into the full message
    list, external_indices into the external segment).
  - Probability (P-036): the stored percent and the recorded
    roll (seed, context, value, passed, seeded) — or None for
    ungated entries, which make no roll by design.
  - Inclusion groups (P-034): the group, the entry's weight,
    the winner's id and the winner's weight/priority when
    excluded.
  - Timed effects (P-033): the config always; the live
    counters and the derived effect ONLY when the caller
    supplied entry_states (a clean-state inspection records
    no counters and says so).
  - Recursion (P-031): the activation via, the scan depth and
    the triggered_by parent for recursive hits, the reference
    depth for {{lore:...}} expansions.
  - Vector matching (P-041): the recorded cosine
    vector_score, the threshold the inspector itself applied
    (when it ran the matcher), the matcher mode/degradation,
    and whether the firing was a true vector hit or the
    honestly-labelled keyword fallback.
  - Scope (P-040): the layer stamped from the caller's scope
    argument (a single-book inspection knows no layer of its
    own).
  - Budget & placement (P-037/P-038, S204): tokens, the budget
    verdict (discard_reason: over_budget / probability_skip /
    scope_over_budget when a layered preview is explained),
    the declared position and the effective role / injection
    depth.
  - Near misses are first-class: an entry that almost fired
    carries near_miss: True, a near_miss_kind and the stage it
    reached (stage_reached). The near-miss kinds are
    secondary_gate_failed, cooldown_suppressed, delay_armed,
    delay_pending, vector_below_threshold, probability_skip,
    over_budget, scope_over_budget and
    inclusion_group_excluded.
  - Honesty (what the engine does NOT record — also returned
    in the payload's facts_not_recorded): probability rolls
    exist only for gated entries; vector scores exist only
    when the matcher ran (caller-supplied vector_hit_ids carry
    no scores, and a precomputed matcher outcome does not
    record the threshold it used); recursive-round (depth > 0)
    secondary-gate near misses are not recorded — the
    near-miss scan covers the round-0 window only;
    {{lore:...}} reference provenance records via/depth, not
    the referring entry's name; timed counters exist only when
    entry_states are supplied; scope_over_budget outcomes are
    produced by the P-040 layered pass, so they appear when a
    layered preview dict is explained via explain_preview, not
    from a single-book tick.
- src/runmal/lorebooks/scan.py — scan_near_misses + the
  NearMiss record: the one scan-level near miss the plain scan
  otherwise drops silently (primary matched, P-032 secondary
  gate refused), with matched keys/counts and full-list
  message indices plus external indices, computed with the
  shared _match_keys core so its semantics cannot drift from
  the scan's.
- src/runmal/lorebooks/preview.py — preview_activation gains
  the opt-in entry_states argument: with a state mapping
  supplied, the tick runs against a COPY (the caller's mapping
  is never mutated, nothing is persisted) and every row gains
  a timed block (config, counters before/after, derived
  effect). Without it, rows are byte-identical to the
  pre-P-043 shape — the preview stays a clean-state tick and
  no timed block is invented.
- src/runmal/lorebooks/router.py — POST
  /lorebooks/{book_id}/inspect (InspectRequest = the preview
  fields plus opt-in recursive_scan): like the preview, but
  every entry's outcome is explained as data (404 for an
  unknown book, 422 for bad scan settings, owner-scoped like
  every lorebook route).
- src/runmal/prompt/inspect.py + prompt/router.py —
  inspect_prompt gains include_activation_inspection
  (default False; the request model exposes it): the trace
  gains lorebook_inspections, one P-043 payload per explicitly
  named lorebook, built by explain_preview over the VERY
  preview dict already computed for the book — never a second
  tick, so a gated entry's recorded roll in the explanation
  is the roll that decided the trace. Scoped (chat_id) layers
  are not separately explained in this slice; their rows keep
  the trace treatment.

## Design decisions recorded

- The inspector is an explanation layer, never a second
  engine: one canonical tick (preview_activation) plus
  recomputation with the engine's own public cores, so an
  explanation cannot drift from the outcome it explains.
- Facts the engine does not record are reported as not
  recorded (facts_not_recorded), never invented — the same
  honesty discipline as P-035's vector rows and P-041's
  fallback labelling.
- No migration: the inspector reads existing rows and
  records only; the migration head stays 0032.

## Tests

- tests/test_p043_activation_inspector.py — 26 tests:
  keyword/gate/message-index explanation, selective pass +
  both near-miss logic modes, direct + external near-miss
  indices, constant/disabled reasons, the seeded roll shown
  and reproducible, no roll for ungated entries, over-budget
  tokens, group exclusion naming the winner, timed
  cooldown/delay/sticky with no caller mutation, the
  clean-state honesty case, preview rows unchanged without
  entry_states, recursive depth + parent, reference
  expansion, caller-id vector hits carrying no invented
  score, below-threshold vector near miss with score, the
  embedder path recording score + threshold, keyword fallback
  honestly labelled, placement + external indices, layered
  scope_over_budget via explain_preview, both endpoints, and
  the no-migration head pin (0032).

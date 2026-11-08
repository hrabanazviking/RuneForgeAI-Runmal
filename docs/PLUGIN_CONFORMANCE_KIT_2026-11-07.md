# P-097 — Plugin conformance kit (2026-11-07)

Roadmap line: "P-097 Plugin conformance kit: a plugin must pass
contract + sandbox tests to be listed (the node-kit pattern
from Yggdrasil)." Design: hidden_files/P097_DESIGN.md; scout:
hidden_files/P097_SCOUT.md.

## What shipped

`src/runmal/plugins/conformance.py` — the conformance gate,
and itself a first-class P-081 citizen (id
`runmal.plugin-conformance`). A plugin is LISTABLE only on a
full pass; until this slice, registration validated pieces of
the contract but nothing ran the sandbox behaviour, checked
the citizen pattern end to end, or produced one inspectable
verdict per plugin.

- **Two submission roads.** The MANIFEST road
  (`check_manifest_data` / `check_manifest`) checks a
  data-shaped submission, optionally with the handlers that
  would be bound for it: with no handlers bound, a manifest
  declaring prompt hooks fails `handlers_binding`, exactly as
  the registry would refuse it, while a data plugin declaring
  no code surfaces can pass on data alone. The CITIZEN road
  (`check_citizen`) runs an in-tree module through the same
  checks plus the citizen-pattern cross-checks.
- **Thirteen checks, fixed order.** Contract: `vocabulary`
  (every capability / permission / event / hook-stage /
  ui-slot name against the P-081 closed sets, each offender
  named individually), `identity` (id grammar, name, strict
  version triple, api_version a real int AND supported),
  `manifest_parses` (the strict P-081 parser), `round_trip`
  (parse → data → parse is stable), `surface_requirements`
  (the P-081 cross-checks re-derived per rule, each unmet
  requirement named), `ui_contributions` (known slot, label,
  int order, JSON-able payload within the 4096-byte canonical
  cap, unique ids), `settings_shape` (storage shape only —
  schema INTERPRETATION is P-098), `handlers_binding`
  (mirrors the registry: declared hooks bound, no undeclared
  handlers, everything callable), `registration` (a THROWAWAY
  registry accepts it and lands REGISTERED; the submission
  dict is byte-identical afterwards; the default registry is
  untouched). Sandbox: `grants_derived`,
  `grants_empty_resources` (in v1 no manifest may hold a
  resource grant — any derived resource is an uninvited
  surface, named, including one smuggled beside another
  refusal), `sandbox_denials` (behavioural probes on a sandbox
  built with no root, no transport, no provider: fetch /
  read / write / secret each refuse; every undeclared known
  capability refuses, every declared one is allowed; grant
  expansion and wider-than-manifest grants refuse ESCALATION;
  the audit log records the denies). Citizen road adds
  `citizen_pattern` (the module exposes the pattern, its
  `build_manifest()` equals its `manifest_data()`, its claimed
  `sandbox_grants()` equal the grants its manifest derives,
  and its `register_plugin` lands REGISTERED under its
  declared id). A check that cannot run reports
  `not_run: <reason>` — never a silent pass, never omitted.
- **The report.** One inspectable JSON-able dict per plugin:
  fixed-order check rows, a flat failure list with stable code
  prefixes naming ids / grants / checks only (never payloads
  or secret values), and a `content_sha256` over the canonical
  JSON of the report core. No timestamps anywhere: the same
  submission yields a byte-identical report, twice.
  `is_listable(report)` is exactly `report passed`;
  `listable_ids(reports)` is the listing gate as data.
- **The corpus.** `citizen_modules()` lists the known
  roadmap-order citizens (P-084..P-095 + the kit itself), then
  DISCOVERS any further module under `runmal.plugins` exposing
  the citizen pattern, sorted by plugin id — so the P-096
  game-bridge citizen (banking in parallel, absent from this
  tree) joins the corpus unchanged on the merged tree, where
  the keeper's banking run re-verifies it.
  `conformance_corpus()` checks every discovered citizen; the
  kit citizen is IN the corpus and passes its own kit. All 14
  citizens in this tree pass as shipped.
- **The kit citizen.** Capabilities `ui.slots` only,
  permissions `ui.contribute` only (P-082 grants EMPTY), no
  events, no prompt hooks, one `settings.panel` contribution
  naming the corpus road. Registered only via
  `register_plugin`; `build_registry` / `create_app`
  untouched. It holds no state — the kit functions are pure.

## Defect found and fixed in the finisher review

- The landed kit reported its checks out of the design's
  fixed order on the parse-failure road: when
  `manifest_parses` failed, the `not_run` rows for
  `handlers_binding` and `registration` were emitted BEFORE
  `settings_shape`, reshuffling the report exactly when a
  submitter most needs to read it in order. Fixed in-slice:
  the two `not_run` rows now land in their own slots, after
  `settings_shape`, and a new battery test pins the fixed
  order on BOTH the passing and the parse-failure roads.
- The previous lead's `grants_empty_resources` repair (a
  smuggled resource grant is named even when grant derivation
  itself refuses on another declaration) was verified in the
  landed tree and is pinned by the battery's
  named-twice fixture.

## Honest limitations

- No HTTP routes in this slice (the P-095 precedent: the
  plugins router is shared with in-flight slices). The gate
  ships as a service surface; wiring `listable_ids` into
  GET /plugins is a keeper / P-100 reconciliation decision,
  never a silent change to an existing road's behaviour.
- The P-082 honesty boundary is inherited verbatim: this is
  an API-surface conformance claim for trusted in-tree
  handlers, NOT an OS/process sandbox claim — a handler that
  bypasses the plugin context it is handed is outside the
  claim; the kit probes the context road.
- P-096 is not in this tree: its citizen joins the corpus by
  discovery at banking, and the keeper's banking run is where
  its pass is verified — this slice claims the 14 citizens
  present here, no more.
- Settings-schema semantics are P-098; failure manners are
  P-099; the third-party gate is P-100. None is pre-empted.

## Tests

`tests/test_p097_plugin_conformance.py` — the kit citizen
(manifest, registration, empty grants), the corpus (every
shipped citizen passes as shipped; deterministic,
byte-identical, twice), passing submissions (minimal data,
UI data, hook plugin with handlers, manifest-object road),
non-mutation of submission and default registry, the fixed
check order on passing AND parse-failure roads, every
deliberate failure named (unknown vocabulary, smuggled
resource permission named twice, unsupported api version,
invalid identity, unmet surface requirements, oversize UI
payload, duplicate hook ids, missing / undeclared hook
handlers, malformed settings, the mega-fixture, a lying
citizen, an incomplete citizen), the listing gate, and the
neighbours (migration head stays 0041, boot registry stays
empty). Counts are recorded in hidden_files/P097_EVIDENCE.md.

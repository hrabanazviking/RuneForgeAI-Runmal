# Failure Manners (P-099) - 2026-11-07

Roadmap line: "Failure manners: a crashing plugin disables
itself with a plain report; the chat never dies with it."

## What landed

`src/runmal/plugins/failure.py` - the manners layer over
the shipped P-081 registry and P-082 sandbox foundations.
Neither foundation changed; `build_registry` /
`create_app` are untouched and no migration was added
(head stays 0041).

- Plain, inspectable reports. `failure_report(registry,
  id)`, `all_failure_reports(registry)` (registration
  order) and `build_failure_report(record)` produce a
  FailureReport: plugin id, state, enabled, self_disabled,
  consecutive strikes, the failure limit, how many
  failures are recorded, the full recorded list and the
  latest failure (plugin, road surface+hook, exception
  CLASS, timestamp, scrubbed message), plus `plain` - a
  deterministic plain-language sentence naming the plugin,
  the latest crash road and class, the strike count,
  whether it has disabled itself, and the one road back.
  HTTP: `GET /plugins/failure-reports` and
  `GET /plugins/{plugin_id}/failure-report` (404 unknown).
- Guarded calls. `guard_plugin_call` /
  `guard_plugin_call_async` wrap ANY host-invoked plugin
  callable in the recording road: a raise is recorded
  through the registry and returned as a GuardOutcome,
  never propagated; the host and siblings carry on. A
  sync guard handed an async callable closes it and
  records a TypeError failure - never a silent drop.
- Sandbox bridge. `sandbox_failure_report(sandbox)`
  renders the P-082 silo in the same shape (quarantine
  named plainly), and `apply_sandbox_bridge(registry,
  sandbox)` mirrors each sandbox failure into the
  registry 1:1 (surface sandbox, hook run, the real
  exception class), watermarked and idempotent. At three
  real failures, sandbox quarantine and registry ERRORED
  agree, so a quarantined citizen is not dispatched on
  other roads. No strikes are ever forged.

## The declared manners

- Containment: every host road (event dispatch, prompt
  hooks, lifecycle - P-081; guarded calls and the sandbox
  bridge - P-099) records a failure before returning.
  No exception from a plugin is swallowed without a
  record, and none raises through a host path.
- Strikes: one recorded failure is one strike; a success
  clears the consecutive count (P-081 rule, kept). At
  FAILURE_LIMIT (3) consecutive strikes an ENABLED plugin
  disables itself: state ERRORED, no dispatch of any
  kind on any road.
- Stays down: a non-ENABLED plugin is never invoked.
  Guarded calls skip it with the reason named
  (not_enabled / unknown_plugin) and the skip is NOT a
  new failure. There is no retry, timer, or auto-re-enable
  anywhere in this layer.
- Deliberate re-enable only: the explicit registry
  enable verb. It CLEARS the strike counter and KEEPS
  the failure history (failure_log + last_error) - the
  declared rule, stated in every report dict.
- Report hygiene: reports carry ids, roads, exception
  classes, timestamps and counts - never payloads.
  Message text appears only scrubbed: scrub_text()
  replaces caller-named secret values with [redacted]
  and caps length. The plain report never embeds message
  text at all, so it cannot leak a secret or a payload
  by construction. Honest boundary: scrubbing hides the
  values the caller names; a value nobody names can
  still appear inside a scrubbed message field, which is
  why the plain report - the surface meant for reading
  aloud - carries no message text whatsoever.

## Honest limitations

- State is process-local, exactly like the P-081
  registry it reports on: reports do not survive a
  restart, and pack-managed durability stays the
  P-083 manager ledger's business.
- The sandbox bridge is an explicit host act: a host
  that never calls apply_sandbox_bridge keeps the two
  records separate (each still correct on its own).
- This is the API-surface manners layer, not an OS
  sandbox (the P-082 honesty boundary stands).

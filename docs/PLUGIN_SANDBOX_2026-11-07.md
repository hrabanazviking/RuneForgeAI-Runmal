# P-082 — Plugin sandbox (2026-11-07)

Roadmap line: "P-082 Plugin sandbox: plugins are data+declared
capabilities; no plugin touches the network/files/secrets
uninvited (ADR-shaped)."

## What landed

`src/runmal/sandbox/` — the enforcement half of the plugin
contract, deliberately independent of the in-flight
`runmal.plugins` package (P-081, team-01): the sandbox consumes
P-081-shaped manifest *data* (dicts in the `manifest_to_data`
shape, or any duck-typed manifest object — the landed
`PluginManifest` qualifies), so P-081 and P-082 reconcile at
banking with no import between them.

- `policy.py` — grant derivation. `grants_from_manifest()`
  turns a manifest into an immutable `GrantSet`. The P-081 v1
  permissions (`chat.read`, `prompt.inject`, `prompt.modify`,
  `ui.contribute`, reserved `chat.write`) are surface
  permissions and grant NO resource access. Resource access is
  granted only by `network.access`, `files.read`,
  `files.write`, `secrets.read` — names deliberately outside
  the v1 manifest vocabulary, so every v1 plugin runs with an
  empty resource grant set: in v1, nothing is invited. Unknown
  names refuse loudly (`UNKNOWN_GRANT`); non-string
  declarations refuse (`MALFORMED_MANIFEST`) — a manifest is
  data, never code. Grant sets cannot widen: `expanded()`
  raises `ESCALATION`, and constructing a `Sandbox` under
  grants the manifest did not declare raises the same.
- `guard.py` — `Sandbox`, the only context a plugin handler
  is handed. Files: grant + realpath confinement to the
  plugin's own root (traversal, absolute and symlink escapes
  refuse `PATH_ESCAPE`). Network: grant + a host-supplied
  transport (none wired → `NO_TRANSPORT`, never an improvised
  socket; http/https only). Secrets: grant + host provider,
  query-by-name only; secret values never appear in errors or
  in the metadata-only audit log. `require_capability()` gates
  host surfaces. `run()` failure-isolates plugin callables:
  exceptions become recorded `RunOutcome`s, never host
  exceptions; three consecutive failures quarantine the
  plugin until the host resets it (P-081 failure-rule shape;
  P-099 refines the manners).
- `docs/adr/0008-plugin-sandbox.md` — the ADR the roadmap
  line asks for, including the rejected alternatives
  (process isolation; scattered checks; unenforced
  declarations).

## The honesty boundary

Per `docs/SECURITY_MODEL.md` section 8 this is an
API-surface boundary for trusted in-tree handlers, not an
OS/process sandbox, and every document in this slice says
so. It confines what a plugin can reach *through the context
it is handed*; handler code itself remains a trust decision
at installation.

## Consumers already lined up

P-083 permission cards record these grants; P-094 data
custody builds on the per-plugin file root; P-097's
conformance kit can test plugins against this contract
mechanically; P-099 refines the quarantine manners.

## Verification

Battery `tests/test_p082_plugin_sandbox.py` plus neighbours
and the full suite — counts in
`hidden_files/P082_EVIDENCE.md`. Migration: none (head stays
0041; the battery pins `0042` absent).

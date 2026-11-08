# ADR-0008 — Plugin sandbox: declared grants behind a guarded context

Status: Accepted
Date: 2026-11-07

## Context

P-081 gives Rúnmál a Plugin API v1: a plugin is a manifest (data)
plus handlers bound at registration by trusted in-tree code. The
manifest declares capabilities and permissions from closed
vocabularies, but a declaration is only a promise until something
enforces it at the point of access. Part VI's roadmap line for
P-082 fixes the requirement: plugins are data+declared
capabilities; no plugin touches the network/files/secrets
uninvited.

`docs/SECURITY_MODEL.md` section 8 sets the honesty bar: Python
extensions execute with server process privileges unless
isolated, extension installation is a code-execution trust
decision, and sandboxing must not be implied unless a real
sandbox boundary exists.

## Decision

- Enforcement lives in `runmal.sandbox`, independent of the
  `runmal.plugins` package: `policy` derives grants from
  P-081-shaped manifest data (dicts or duck-typed manifest
  objects), and `guard.Sandbox` is the only context a plugin
  handler is handed.
- Grants are subtraction-only. The P-081 v1 permissions are
  *surface* permissions (chat/prompt/UI) and grant no resource
  access. Resource access (network, files, secrets) is granted
  only by the sandbox resource permissions `network.access`,
  `files.read`, `files.write`, `secrets.read` — names that are
  deliberately NOT in the v1 manifest vocabulary, so a v1 plugin
  runs with an empty resource grant set. A future API version
  that admits them into the vocabulary is enforced by this
  policy unchanged.
- Unknown permission/capability names refuse loudly at grant
  derivation; grant sets are immutable; handing the sandbox
  grants beyond the manifest refuses as escalation at
  construction. There is no runtime widening operation.
- Every resource verb checks its grant before touching a
  backend. Files additionally confine to the plugin's own root
  (realpath; traversal, absolute and symlink escapes refuse).
  Network requires a host-supplied transport — there is no
  default socket. Secrets are query-by-name against a
  host-supplied provider; values never appear in errors or in
  the metadata-only audit log.
- Plugin execution through the sandbox is failure-isolated:
  exceptions become recorded outcomes, never host exceptions,
  and three consecutive failures quarantine the plugin until
  the host resets it (the P-081 failure rule's shape; P-099
  refines the manners).

## Consequences

- The boundary is an API-surface boundary: it confines what a
  handler can reach through the context it is handed. It is
  NOT an OS/process sandbox and no document claims it is one;
  handler code remains trusted in-tree code, exactly as
  SECURITY_MODEL section 8 requires us to say.
- P-083 (plugin manager) records these grants on its permission
  cards; P-094 (data custody) builds on the per-plugin file
  root; P-097 (conformance kit) can test a plugin against this
  contract mechanically.
- Deny-by-default costs convenience: a plugin that wants the
  network in a future API version must declare it and the host
  must wire a transport. That friction is the point.

## Alternatives considered

- An OS/process sandbox (subprocess + seccomp/namespaces):
  a real isolation boundary, but a platform project of its own
  and disproportionate for v1's trusted in-tree handlers;
  rejected for this slice, not forever.
- Permission checks scattered through the host services:
  unenforceable by audit — a missed call site is a silent
  grant. Rejected; one facade, one audit log.
- Trusting the manifest without enforcement: declarations as
  documentation. Rejected by the roadmap line itself.

## Evidence / references

- Roadmap P-082 line, `docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`.
- `docs/SECURITY_MODEL.md` sections 8 and 13.
- P-081 design (manifest vocabularies, failure rule) as landed
  in team-01's `runmal.plugins` work.
- Battery: `tests/test_p082_plugin_sandbox.py`.

## Supersession

None. A future process-isolation ADR would supersede the
boundary paragraph, not the grant policy.

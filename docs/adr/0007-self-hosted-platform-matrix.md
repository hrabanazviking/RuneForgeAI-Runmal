# ADR-0007 — Self-hosted platform matrix (S805 redefined)

Status: Accepted
Date: 2026-10-13

## Context

S805's roadmap definition called for a CI platform matrix — at least
Linux + Windows core tests. The implementation first took the
conventional shape, a GitHub Actions workflow
(`.github/workflows/ci.yml`), but the forge's GitHub credentials
cannot push workflow files (the OAuth token lacks the `workflow`
scope; the backup PAT lacks Workflows permission), and the slice
stalled at 93/94 on that credential wall.

## Decision (Volmarr, 2026-10-13)

Volmarr ruled the hosted-CI approach itself out:

> "don't rely on Microsoft's AIs. Test it yourself and don't worry
> about them. I will never pay for Microsoft's forced AI strategy."

and re-confirmed:

> "just push without the need for Microsoft's CI crap"

So S805 is implemented as a **self-run platform matrix**:

1. **The harness is ours.** `runmal release matrix`
   (`runmal.release.matrix`) runs the core test suite — the ordinary
   `pytest -q` suite — in the current environment on project-owned
   hardware and records a structured evidence leg: hostname, OS,
   machine architecture, Python implementation/version, the exact
   command, exit code, duration, and the suite summary line.
2. **Evidence is durable and in-repo.** Legs are written as JSON
   (schema `runmal.platform-matrix/v1`) and summarised in
   `docs/PLATFORM_MATRIX.md`. A leg that never ran is recorded as
   not run; no result is ever inferred across machines.
3. **Hosted CI is deliberately not used.** No `.github/workflows/`
   file ships. Nothing in the release path gates on GitHub Actions
   or any other hosted CI.
4. **The fleet defines the matrix.** There is no Windows machine in
   the fleet and none will be rented from Microsoft, so the Windows
   leg does not run; the matrix document states that plainly rather
   than hiding the gap. Platform-specific unsupported cases (e.g.
   hardware-dependent voice tests) surface as explicit skips in the
   suite output, named in the matrix record — never hidden.

The roadmap definition itself is untouched: S805's *acceptance
intent* — core tests proven across the project's platforms, with
unsupported cases explicit — is met by self-hosted evidence instead
of a hosted runner matrix. This substitution is recorded in
`docs/STATUS.md` and the Forge-Log so the change of mechanism is
never mistaken for a silent reinterpretation.

## Consequences

- Release verification runs where the project runs: on the forge
  laptop (purplelongship) for the Linux leg today; any future
  machine joins the matrix by running the same command and
  committing its evidence leg.
- The suite itself remains the gate (exit code + summary recorded);
  the harness adds evidence, not a second test framework.
- The abandoned Actions commit (local branch `s805-ci-workflow`)
  is deleted once this replacement lands and verifies.

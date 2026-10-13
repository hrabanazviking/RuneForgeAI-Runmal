# Rúnmál Platform Matrix (S805)

S805 is a **self-run** platform matrix. Volmarr's ruling of
2026-10-13 (ADR-0007) replaced the hosted-CI design outright:

> "don't rely on Microsoft's AIs. Test it yourself and don't worry
> about them."

> "just push without the need for Microsoft's CI crap"

There is **no GitHub Actions workflow** in this repository and
nothing in the release path waits on hosted CI. The matrix runs on
the project's own machines via the release tooling:

```sh
runmal release matrix --out docs/platform-matrix/<date>-<host>.json
```

The harness (`runmal.release.matrix`) executes the core suite — the
ordinary `pytest -q` run over `tests/` — and records one evidence
leg per machine: hostname, OS and release, architecture, Python
implementation and version, the exact command, duration, exit code,
and the suite's own summary line. Evidence files live in
`docs/platform-matrix/` (schema `runmal.platform-matrix/v1`).

## Legs

| Leg | Machine | OS / Python | Result |
|---|---|---|---|
| Linux (x86_64) | purplelongship (forge laptop) | _recorded in the evidence leg_ | _pending — filled by the real run_ |
| Windows | — | — | **not run** — there is no Windows machine in the fleet and none will be rented from Microsoft; the gap is stated, not hidden |

## Reading the evidence

- A leg's `suite.status` is `passed` only when the suite exited 0.
- Skips are part of the record, not a footnote: the suite summary
  line is stored verbatim, and hardware/provider-dependent tests
  that cannot run on a leg skip explicitly (they never pass
  silently, and a leg never borrows another leg's result).
- Tagged hardware/provider jobs stay separate from the core suite,
  exactly as the roadmap intended — they are opt-in runs with their
  own evidence (see `docs/BENCHMARKS.md`).

## Adding a leg

On any project machine: install the project (`pip install -e
".[dev]"` plus the extras that machine exercises), then run the
command above and commit the JSON leg with an updated row in the
table. The matrix is the set of legs that actually ran — nothing
more, nothing less.

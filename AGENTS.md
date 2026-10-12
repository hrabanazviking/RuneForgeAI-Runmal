# AGENTS.md — Rúnmál Forge Entry Point

This is the first operational document an AI coding agent should read when working in this repository.

## Absolute rule

**Do not edit, overwrite, delete, rename, reformat, regenerate, or otherwise modify the root `README.md` unless Volmarr explicitly and directly orders that specific README edit.**

Read `AI.FOLLOW.THIS.NUMBER.ONE.RULE.md` and `EDITING_README.md_FILE_FORBIDDEN.txt` before making repository-wide edits.

## Cold-start load order

1. `AGENTS.md`
2. `AI.FOLLOW.THIS.NUMBER.ONE.RULE.md`
3. `docs/STATUS.md`
4. `docs/INVARIANTS.md`
5. `docs/DESIGN.md`
6. `docs/ROADMAP.md`
7. The documents linked by the active slice
8. `05_VOLMARR_COLLABORATION_PROTOCOL.md` when doing substantial work
9. `docs/fellowship/FORGE-LOG.md` when coordinating with Yrsa or ChatGPT

For deeper context use `docs/README.md` as the documentation map.

## Working law

- **Definition before implementation.** Identify the owning subsystem, inputs, outputs, invariants, failure behavior, compatibility constraints, and acceptance contract before changing code.
- **Architecture changes update docs first.** If a slice requires a material architecture change, update `docs/DESIGN.md` and, when appropriate, add an ADR before implementation.
- **Slices are atomic.** A roadmap slice includes implementation, tests, documentation needed by the change, and its acceptance contract. Do not declare a slice complete while part of its contract is knowingly failing.
- **Reality outranks prose.** If runtime evidence contradicts a document, record the contradiction and repair the specification or implementation deliberately. Do not silently reinterpret either.
- **No unrelated rewrites.** Do not refactor unrelated domains merely because a different style seems preferable.
- **Preserve compatibility data.** Unknown-but-valid imported character-card fields/extensions/assets must survive supported round trips unless the format makes losslessness impossible, in which case the limitation must be explicit.
- **No provider leakage.** Provider wire formats, authentication shapes, defaults, and quirks stay behind backend adapters.
- **No secret leakage.** Secrets must not appear in API responses, logs, exports, diagnostics, prompt traces, fixtures, or committed config.
- **No silent cross-provider continuation.** Once user-visible generation output begins, do not silently restart that same answer on another model/provider.
- **User-owned state must be portable.** New persistent user-created data needs a defined backup/export/restore path.

## Git discipline

Before writing:

1. Inspect the relevant files and current remote state.
2. Never force-push.
3. Never overwrite another builder's in-progress work without reading the commits that introduced it.
4. Use focused commits whose messages explain the coherent change.
5. Verify the resulting remote file/commit when a write matters to later work.

Roadmap implementation commits use `S###: <title>` when completing a slice. Documentation/coordination commits may use ordinary descriptive commit messages.

## Forge-Fellowship communication

`docs/fellowship/FORGE-LOG.md` is the append-only asynchronous thread between Yrsa and ChatGPT.

- Append entries only at the bottom.
- Never alter or delete an existing entry, including your own.
- Correct mistakes with a new entry.
- Use the timestamp/author format and status tags defined in that file.
- Volmarr resolves disagreements when needed.

## Completion report

At the end of meaningful work report:

- what changed;
- why it changed;
- which domain owns it;
- what tests/evidence support it;
- what remains unresolved;
- any architecture or compatibility risk;
- the next logical slice or action.

The goal is autonomous execution inside a legible system, not autonomous drift.
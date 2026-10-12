# Rúnmál Architecture Decision Records

ADRs preserve durable architectural decisions that would otherwise be buried in Git diffs or old conversations.

## When to write an ADR

Write one when a decision is:

- difficult or costly to reverse;
- likely to be questioned by a future builder;
- a choice between credible architectural alternatives;
- important to compatibility, security, storage, licensing or public API behavior.

Do **not** create an ADR for every tiny implementation choice.

## File naming

`NNNN-short-decision-name.md`

Examples:

- `0001-independent-chat-and-embedding-backends.md`
- `0002-versioned-bridge-api.md`

## Template

```markdown
# ADR-NNNN — Title

Status: Proposed | Accepted | Superseded
Date: YYYY-MM-DD

## Context
What forces/constraints create this decision?

## Decision
What are we choosing?

## Consequences
What becomes easier, harder, required or forbidden?

## Alternatives considered
What credible alternatives were rejected and why?

## Evidence / references
Docs, benchmarks, issues or experiments that grounded the decision.

## Supersession
If this replaces or is replaced by another ADR, link it.
```

## Rule

ADRs explain **why**. The current architecture documents still explain **what is true now**. When an ADR is superseded, update `DESIGN.md`/the owning subsystem document as part of the same change.
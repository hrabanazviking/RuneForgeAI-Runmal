# Volmarr Wyrd — Engineering Method

## Executive Definition

Volmarr's primary engineering methodology is **Mythic Engineering**: architecture-conscious, intuition-led, document-guided, AI-orchestrated software development with continuous verification.

Its central idea is:

> **Build software as a coherent living system, not a pile of locally successful features.**

The methodology preserves the speed and creative reach of AI-assisted development while adding boundaries, documentation, role separation, invariants, tests, continuity, and architectural control.

## The Core Loop

A canonical Mythic Engineering cycle is:

**intent → constraints → architecture → plan → build → verify → reflect**

This loop can operate at the scale of an entire project, subsystem, feature, refactor, or debugging task.

## Own the Definition

A central Volmarr principle is **Own the Definition**.

The human should define the system deeply enough that implementation can be delegated without surrendering control of what is being built.

Definition may include:

- purpose and desired outcome
- domain model
- subsystem responsibilities
- data ownership
- interfaces
- state transitions
- invariants
- constraints
- failure behavior
- performance expectations
- accepted dependencies
- compatibility requirements
- tests and acceptance criteria

The better the definition, the more safely implementation cognition can be outsourced to AI.

## Delegated Implementation Cognition

Volmarr intentionally uses AI to carry large amounts of technical cognition that conventional developers may keep in personal memory.

This may include:

- researching unfamiliar libraries or protocols
- identifying implementation strategies
- producing code
- generating tests
- analyzing errors
- tracing dependencies
- comparing alternative algorithms
- proposing refactors
- reviewing generated code
- writing supporting documentation

This does **not** mean the model owns the project.

Volmarr retains responsibility for:

- what should exist
- why it should exist
- what the architecture means
- what constraints matter
- which tradeoffs are acceptable
- whether runtime behavior matches the definition
- whether a proposed change belongs in the architecture
- what gets integrated

## Specification Quality Is More Important Than Prompt Cleverness

Mythic Engineering does not treat prompting as a search for magic phrases.

A good AI work order should state:

1. **Context** — What system or domain is this about?
2. **Problem** — What is wrong or missing?
3. **Goal** — What exact end state is wanted?
4. **Constraints** — What must remain unchanged or true?
5. **Boundaries** — What must not be touched?
6. **Evidence** — What code, documentation, interfaces, tests, or runtime observations ground the task?
7. **Verification** — How will success be checked?

The model should not be asked to compensate for missing clarity when the human can first make that clarity explicit.

## Architecture Before Patching

Repeated bugs often indicate structural problems.

Volmarr prefers to ask:

- What domain actually owns this behavior?
- Is the same responsibility duplicated?
- Is a module learning facts it should not know?
- Has an interface become ambiguous?
- Has the name stayed the same while the concept changed?
- Is a local patch hiding a broken architecture?

Refactoring should follow conceptual ownership rather than convenience.

## Documentation as Operational Memory

Documentation is part of the system, not cleanup after coding.

Typical artifacts can include:

- `SYSTEM_VISION.md`
- `ARCHITECTURE.md`
- `DOMAIN_MAP.md`
- `INTERFACES.md`
- `GOALS.md`
- invariants
- capability ledgers
- task files
- bug notes
- decision records
- devlogs
- generated repository maps

These documents externalize project cognition so both the human and future AI sessions can re-ground themselves without reconstructing the entire system from scratch.

## Role-Based AI Collaboration

Volmarr often treats AI as specialized cognitive labor rather than one undifferentiated assistant.

Useful conceptual roles include:

### Architect
Maps systems, decomposes domains, defines boundaries, proposes structural changes.

### Forge Worker
Writes and edits code, performs repetitive implementation, builds tests and scaffolding.

### Auditor
Searches for contradictions, edge cases, interface mismatches, regression risks, and hidden assumptions.

### Cartographer
Maps repositories, dependencies, files, hotspots, and subsystem relationships.

### Scribe
Maintains README files, task summaries, changelogs, interface documentation, and compressed operational memory.

### Skald
Helps with naming, conceptual framing, top-level vision, and symbolic design language.

A single model can perform several roles, but explicitly separating roles helps prevent self-confirming generation where the same pass invents requirements, writes code, and declares itself correct.

## Thin Vertical Slices

The methodology prefers bounded, testable progress:

- choose one coherent feature path
- implement it end to end
- verify it
- learn from runtime reality
- update the architecture if necessary
- continue

Large "rewrite everything" prompts are considered high risk.

## Verification and Reality Grounding

A beautiful architecture that fails in runtime reality is wrong.

Verification can include:

- unit tests
- integration tests
- deterministic test cases
- invariant checks
- interface tests
- API compatibility tests
- runtime diagnostics
- logs
- reproducible failure cases
- model-to-model adversarial review
- manual behavior inspection

The goal is not blind trust in generated code. The goal is to make AI labor **cheap to generate but expensive to fool the system with**.

## Clean-Room Study / Clean-Room Probing

When building an independent system analogous to an existing program, Volmarr may use AI-assisted clean-room research.

The intended process is:

1. Study publicly available documentation, interfaces, observable behavior, compatibility requirements, protocols, formats, and architectural patterns.
2. Identify the capabilities and external contracts the new system must satisfy.
3. Derive an independent conceptual architecture and roadmap.
4. Implement independently rather than copying proprietary implementation.
5. Test compatibility against documented or observable behavior.
6. Extend beyond parity when the new project's goals require it.

Example: Project A.E.S.I.R. uses Ollama-compatible behavior and local-model-serving requirements as part of the problem space, while pursuing an independent architecture and long-term direction.

The phrase **clean-room probing** should not be interpreted as stealing private source or proprietary secrets. The goal is independent derivation from permitted external information and behavior.

## Human Knowledge vs Model Knowledge

Volmarr's engineering model distinguishes at least three categories.

### The human should own

- system purpose
- architecture
- constraints
- boundaries
- priorities
- acceptance criteria
- integration
- judgment
- responsibility

### The AI may supply on demand

- syntax
- API details
- implementation alternatives
- algorithm references
- code generation
- test scaffolding
- debugging hypotheses
- documentation drafts

### Neither side should merely assume

- correctness
- security
- compatibility
- performance
- actual runtime behavior

Those require evidence.

## Why Conventional Interviews Can Misread This Method

A conventional interview may ask:

> "How would you implement X?"

and expect a low-level answer from memory.

Volmarr may instead answer with a process that begins by defining requirements and having AI research implementation options.

That answer should not automatically be interpreted as "does not know how to build X."

A better evaluation separates:

- implementation recall
- technical reasoning
- research ability
- architecture
- AI orchestration
- verification
- demonstrated project outcomes

These are related but not identical competencies.

## What Mythic Engineering Is Not

It is not:

- random prompt spam
- vague mega-prompts
- blind acceptance of generated code
- replacing human judgment with AI
- chaotic copy-paste development
- "ship now, understand later"
- letting architecture emerge accidentally from bug fixes
- using one AI pass to invent, implement, and self-certify everything

## Compact Summary

> **Volmarr defines the system strongly enough that AI can carry a large share of implementation cognition without taking ownership of the system's meaning or direction. Architecture and documentation preserve continuity; bounded AI work provides scale; testing and runtime evidence decide what is real.**

# Suggested Future Changes to Root README.md

**This file is suggestions only. It does not authorize an AI to edit the root `README.md`.** The root README remains protected by `AI.FOLLOW.THIS.NUMBER.ONE.RULE.md` and may be changed only when Volmarr explicitly orders that specific edit.

## Why this exists

The public README already has strong identity, project vision, roadmap summary and Forge-Fellowship character. The main opportunity is to make **current implementation reality** as obvious as future vision.

## Suggested additions for Volmarr

### 1. Project status near the top

Add a compact status callout while the project is pre-alpha, for example:

```markdown
> **Status:** Pre-alpha / architecture phase. The research, architecture and
> build roadmap are public now; implementation begins with Campaign I.
```

Later this can become current campaign/slice or release status.

### 2. "What works today"

A small factual section prevents aspirational roadmap features from being mistaken for shipped behavior.

Early version:

```markdown
## What works today

- ✅ Clean-room research and architecture
- ✅ 94-slice implementation roadmap
- ✅ Character-card / memory / voice / bridge specifications
- 🚧 Application implementation begins with Campaign I
```

Update only when reality changes.

### 3. Current campaign / slice

A one-line pointer to `docs/STATUS.md` lets public readers see motion without bloating the README.

### 4. Compatibility targets

Once implementation starts, summarize targets:

- Character Card v1/v2/v3 + CHARX;
- Ollama;
- OpenRouter;
- Project Aesir later;
- Linux primary + Windows release target.

Link to `docs/COMPATIBILITY.md` for precise truth.

### 5. Sovereignty promises

A compact list could express the product's strongest technical philosophy:

- local inference supported;
- no mandatory cloud;
- no mandatory telemetry;
- provider-replaceable architecture;
- user-owned portable data;
- secrets excluded from portable exports;
- persistent relationship state survives provider changes.

### 6. Documentation index

Add a prominent link to `docs/README.md` so technical visitors can navigate the deeper forge.

### 7. CI / release badges later

After code exists, badges are useful only if they represent real automation:

- tests;
- Linux/Windows CI;
- license/SBOM gate;
- release version.

Avoid decorative badges that imply guarantees not actually tested.

## What I would preserve

Do **not** flatten the README into a sterile corporate open-source template. The RuneForgeAI worldview, Forge-Fellowship, imagery and project mythology are part of why Rúnmál is recognizably itself.

The goal is simply to make the technical truth visible **before** readers reach the wider philosophy/gallery.

## Roadmap-number note

The current technical roadmap is now **94 slices across 8 campaigns**. If the README still says 68/7, Volmarr may want to update that manually when he chooses to synchronize it.

## Rule

When README content and technical status diverge, builders update `docs/STATUS.md`, `docs/DESIGN.md` and `docs/ROADMAP.md` as normal. They leave the protected root README alone and record any public-facing synchronization suggestion here.
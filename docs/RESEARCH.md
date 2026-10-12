# RESEARCH.md — Rúnmál Clean-Room Research Ledger

*Started 2026-10-12 by Yrsa's research coordination and strengthened by ChatGPT review. This is original synthesis of public specifications, documentation, observable interfaces and independent analyses. No SillyTavern or other studied project's source code is copied into Rúnmál.*

**Clean-room rule:** study capabilities, public formats, protocols, documented behavior and architectural ideas; derive Rúnmál's requirements and implementation independently.

## How to use this document

Research is evidence, not architecture. `DESIGN.md` and the subsystem documents own Rúnmál's actual design. When research changes, update the owning design/roadmap contract deliberately.

For load-bearing decisions, prefer sources in this order:

1. normative specification;
2. official project/API documentation;
3. upstream repository/release notes;
4. upstream issue/discussion;
5. research paper/benchmark with reproducible context;
6. secondary technical analysis.

A secondary source is useful for discovery but should not outrank a current normative spec.

### Verification labels

- **VERIFIED-DOC** — current primary/normative documentation checked.
- **VERIFIED-RUNTIME** — reproduced locally against a recorded version/hardware configuration.
- **CANDIDATE** — promising choice, implementation/runtime proof still required.
- **UNVERIFIED** — do not build a hard contract on it yet.
- **REVERIFY-AT-BUILD** — API/license/version is fast-moving enough that the slice must check again.

---

# 1. Character cards and compatibility

## 1.1 Character Card v2

Character Card v2 formalizes a `chara_card_v2` data structure beyond the old flat v1 fields. Relevant concepts include distinct description/personality/scenario/example-dialogue fields, alternate greetings, creator metadata, system/post-history prompt fields, embedded lorebook/world-info data and opaque extension data.

Primary source: https://github.com/malfoyslastname/character-card-spec-v2

**Rúnmál verdict: LEARN/COMPATIBILITY TARGET.** Preserve distinct field roles and opaque extension data. Metadata such as creator notes is not automatically prompt material.

Status: **VERIFIED-DOC / REVERIFY-AT-BUILD**.

## 1.2 Character Card v3 and CHARX correction

Important correction from the first draft of this research: the current v3 archive/container name is **CHARX**, not XCHAR. The v3 repository itself warns that older `concepts.md` material is outdated; the normative/current specification should be used when they disagree.

Primary source: https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md
Repository/concept warning: https://github.com/kwaroran/character-card-spec-v3/blob/main/concepts.md

V3 adds richer assets/metadata and archive packaging beyond JSON/PNG. Rúnmál therefore needs safe CHARX import/export rather than claiming v3 compatibility from PNG `ccv3` parsing alone.

**Rúnmál verdict: LEARN AGGRESSIVELY.** Current normative v3 spec is the compatibility authority; tolerate older legal variants on import, emit a deliberate supported version on export, and preserve unknown compatible fields/assets.

Status: **VERIFIED-DOC / REVERIFY-AT-BUILD**.

## 1.3 PNG card containers

Character cards commonly embed base64 JSON in PNG textual metadata chunks (`chara`, and v3-compatible `ccv3` where specified). Export code must create valid PNG chunks/checksums and import must treat the image as untrusted input.

Implementation requirements derived for Rúnmál:

- bounded file size;
- legal chunk parsing;
- typed malformed-input errors;
- unknown compatible metadata preservation;
- semantic round-trip tests rather than requiring byte-identical regenerated PNGs.

Status: **CANDIDATE until fixture corpus proves behavior.**

---

# 2. Lorebooks, prompt templates and group chat

## 2.1 Lorebook/world-info model

Studied systems converge on an entry model containing activation keys, secondary/selective keys, constant entries, insertion position/order, priority, probability and timed behavior such as sticky/cooldown/delay. Recursive activation is useful but creates cycle/debugging hazards.

Useful public documentation/examples:

- https://docs.sillytavern.app/usage/core-concepts/worldinfo/
- https://github.com/sillytavern/sillytavern-docs

**Rúnmál verdict: ADAPT.** Keep the expressive activation model while making resolution deterministic and inspectable. Add hard recursion bounds/cycle detection and Prompt Trace rather than inheriting opaque activation behavior.

Status: **VERIFIED-DOC at concept level / REVERIFY-AT-BUILD for exact imported fields.**

## 2.2 Prompt templates

The transferable idea is a prompt as an ordered set of semantically named blocks, not one giant hand-concatenated string. Depth injection/Author's Note works because position in context matters.

**Rúnmál extension:** typed slots, explicit response-budget reservation, stable priority/trim policy and a Prompt Trace explaining inclusion/discard.

Status: **DESIGN DERIVATION** rather than a compatibility requirement.

## 2.3 Group chats

Studied group-chat systems use manual, name/talkativeness-driven, round-robin/list and pooled/random speaker strategies. Community experience also shows that an LLM/director pass can improve staging when ordinary heuristics allow every character to speak at once or spotlight one character indefinitely.

Primary documentation starting point: https://docs.sillytavern.app/usage/core-concepts/groupchats/

**Rúnmál verdict: ADAPT.** Ship deterministic built-in speaker policies behind a pluggable policy interface; allow a future director without coupling group storage to one policy.

---

# 3. Extension architecture

SillyTavern demonstrates the value of lifecycle events, extension-owned settings and prompt-injection points, but its browser/server split is not a requirement for Rúnmál.

Primary docs: https://docs.sillytavern.app/for-contributors/writing-extensions/

**Rúnmál verdict: ADAPT.** Use server-side Python hooks with typed payloads and named prompt slots. An installed Python extension is trusted server code unless a real sandbox is built; documentation must not imply sandboxing that does not exist.

---

# 4. Backend/provider research

## 4.1 Why Rúnmál needs its own seam

"OpenAI-compatible" providers still differ in streaming framing, parameter support, model IDs, default behavior, capability metadata, auth and errors. Provider details therefore belong inside adapters.

Rúnmál now separates:

- `ChatBackend`;
- `EmbeddingBackend`;
- `STTBackend`;
- `TTSBackend`.

This permits cloud chat + local embeddings/voice and prevents conversational model changes from silently invalidating the memory vector space.

See `BACKEND_CONTRACT.md`.

## 4.2 Ollama

Official API documentation:

- Chat: https://docs.ollama.com/api/chat
- Embeddings: https://docs.ollama.com/api/embed
- OpenAI compatibility: https://docs.ollama.com/api/openai-compatibility

### Correction: embeddings endpoint

The first research draft referred to native `/api/embeddings`. Current official Ollama native documentation uses **`POST /api/embed`**. Implementation must re-check the official docs when S304 is built.

Native Ollama is attractive because it exposes Ollama-specific controls/metadata directly rather than forcing all behavior through an OpenAI compatibility shim.

**Rúnmál verdict:** native adapter first; OpenAI compatibility is useful knowledge but not the internal Rúnmál contract.

Status: **VERIFIED-DOC 2026-10-12 / REVERIFY-AT-BUILD**.

## 4.3 OpenRouter

OpenRouter presents an OpenAI-compatible chat API with namespaced model IDs and provider-routing behavior.

Official docs entry points:

- https://openrouter.ai/docs/api/reference/overview
- https://openrouter.ai/docs/api/reference/chat-completion

**Rúnmál verdict:** implement an adapter that hides routing/model/error/auth differences behind normalized events and capabilities. Do not let OpenRouter model slugs become domain identifiers outside backend metadata.

Pricing/fee/logging/provider-data-policy details are fast-moving and should be checked directly before financial or privacy claims are made in user-facing docs.

Status: **VERIFIED-DOC at API-shape level / REVERIFY-AT-BUILD for policy/pricing details**.

## 4.4 Aesir

Rúnmál should encourage Project Aesir to expose a convenient OpenAI-compatible external server surface where useful, but the internal Rúnmál contract remains independent.

Required capabilities for low-friction integration:

- streaming generation with terminal done/error state;
- explicit supported/unsupported sampling controls;
- model/context metadata;
- cancellation behavior;
- embeddings or an explicit unsupported declaration.

**Rúnmál verdict:** Campaign VII adapter must pass the same contract suite as other backends.

---

# 5. Storage and retrieval

## 5.1 SQLite

SQLite fits a local single-user application: zero service administration, transactional semantics, portable file and mature recovery tools.

Primary docs:

- https://www.sqlite.org/docs.html
- Backup API: https://www.sqlite.org/backup.html
- WAL: https://www.sqlite.org/wal.html
- Foreign keys: https://www.sqlite.org/foreignkeys.html

**Rúnmál additions:** migrations from the first schema, foreign-key enforcement, explicit WAL/busy-timeout policy and safe online backup. A live DB should not be documented as safely backed up by arbitrary file copy.

Status: **VERIFIED-DOC**.

## 5.2 sqlite-vec

sqlite-vec offers a zero-extra-service vector option living near the SQLite data model.

Primary repo: https://github.com/asg017/sqlite-vec

Its pre-1.0/evolving nature is exactly why Rúnmál isolates vector operations behind its own store interface.

**Rúnmál verdict: CANDIDATE PRIMARY.** Keep FTS5 as graceful fallback and a rebuild path if vector representation changes.

Status: **CANDIDATE / REVERIFY-AT-BUILD**.

## 5.3 FTS5

SQLite FTS5 provides local keyword retrieval and a crucial fallback during embedding-provider outages/migrations.

Primary docs: https://www.sqlite.org/fts5.html

**Rúnmál verdict: LEARN/USE.** Memory retrieval should never become unusable solely because a vector backend is unavailable.

---

# 6. Living-memory research

Simple long-term-memory systems often converge on:

1. extract facts/events;
2. embed them;
3. retrieve semantically at generation time.

That is useful but incomplete. Long-lived companion memory also needs:

- source provenance;
- witness scope;
- temporal state;
- contradiction/supersession;
- duplicate consolidation;
- message-mutation synchronization;
- ability to rebuild derived memory/indexes;
- an explanation of why something was recalled.

These additions are Rúnmál architecture derived from known failure modes rather than compatibility requirements.

See `MEMORY_ARCHITECTURE.md`.

**Key research conclusion:** vectors answer "what is nearby in embedding space?" They do not by themselves answer "what is currently true, who knows it, and why do we believe it?"

---

# 7. Real-time voice research

Target experience: local/sovereign conversational voice with interruption and approximately human-feeling latency on Volmarr's available hardware. Internet benchmark numbers are hypotheses until measured on the actual Ryzen 9 system.

## 7.1 VAD — Silero

Silero VAD is a small, widely used neural VAD with streaming-friendly inference.

Primary repo: https://github.com/snakers4/silero-vad

**Rúnmál verdict: CANDIDATE DEFAULT.** Use pre-roll, hysteresis/state and a separate endpointing policy. VAD answers speech presence; endpointing decides conversational turn completion.

Status: **CANDIDATE / VERIFY-RUNTIME in S502**.

## 7.2 STT — faster-whisper baseline

faster-whisper uses CTranslate2 to run Whisper models efficiently and supports word timestamps/VAD filtering patterns useful for local speech recognition.

Primary repo: https://github.com/SYSTRAN/faster-whisper

**Rúnmál verdict:** `small` int8 is a sensible initial Ryzen-9 baseline, but S503 must define an accuracy/RTF bar before benchmarking rather than laundering an internet estimate into a requirement.

Status: **CANDIDATE / VERIFY-RUNTIME**.

## 7.3 TTS — Kokoro direction and dependency-tree warning

Kokoro is attractive because its model lineage is permissively licensed and lightweight relative to many cloning systems.

Primary model/repo starting points:

- https://huggingface.co/hexgrad/Kokoro-82M
- https://github.com/hexgrad/kokoro
- ONNX wrapper: https://github.com/thewh1teagle/kokoro-onnx

### Critical correction

A permissively licensed model and top-level wrapper do **not** prove that the runtime distribution is entirely permissive. Current wrapper/phonemization dependency choices can pull additional components whose licenses must be audited independently (including eSpeak-related paths in some configurations).

Misaki is one relevant phonemization project to evaluate: https://github.com/hexgrad/misaki

eSpeak-NG license/source must be treated according to its own upstream licensing: https://github.com/espeak-ng/espeak-ng

**Rúnmál verdict:** Kokoro remains a strong **candidate**, not an already-closed licensing decision. S504 moves the complete dependency/model/voice/phonemization license audit ahead of acceptance.

Status: **CANDIDATE / LICENSE GATE REQUIRED**.

## 7.4 Piper and XTTS policy

Do not select a voice runtime merely because it is fast or popular. Rúnmál's distribution policy requires compatible licensing across code, model weights, voices and dependencies. The maintained Piper ecosystem and XTTS-family model licensing must be checked at implementation/distribution time rather than copied from stale summaries.

**Rúnmál rule:** the release SBOM/license gate decides what can ship.

## 7.5 Full-duplex orchestration

The important architecture is a preemptible state machine:

```text
mic → VAD → STT → turn coordinator → LLM stream → TTS → playback
                 ↘ barge-in cancellation path ↗
```

Correctness hazards:

- self-interruption/echo;
- treating backchannels as interruption;
- slow endpointing;
- generated text being stored as if fully heard after interruption.

The last hazard motivates Rúnmál's playback-truth ledger. Exact spoken history requires playback evidence; text generation alone is insufficient.

## 7.6 VRChat room audio

OSC is useful for controls/avatar parameters/events but is not equivalent to capturing the room's voice audio. A PC-host companion that "hears the whole room" needs an explicit audio-ingress route from the VRChat host machine, plus self-output separation/AEC strategy.

**Rúnmál verdict:** split OSC reference integration from room-audio ingress in Campaign VI.

---

# 8. Web/backend stack

## 8.1 FastAPI

FastAPI is a mature async Python API framework with OpenAPI/Pydantic ecosystem fit for Rúnmál.

Official docs: https://fastapi.tiangolo.com/

**Rúnmál verdict: USE.** SSE/streaming response for one-way token output; WebSocket reserved for genuinely bidirectional voice/audio sessions where useful.

## 8.2 SSE vs WebSocket

Text token streaming is fundamentally server→client, so SSE/streaming HTTP is sufficient and reconnect/debugging-friendly. Voice requires two-way low-latency media/control and justifies WebSocket or another bidirectional transport.

Never proxy provider stream bytes directly to the browser; normalize them first.

## 8.3 Jinja + htmx + Alpine/vanilla JS

Rúnmál does not need a mandatory Node/SPA build stack for chat CRUD and server-driven pages. htmx/Jinja can keep most state server-side while voice uses a small dedicated JS island.

Official htmx docs: https://htmx.org/docs/

**Rúnmál verdict: USE initially, preserve API-first replacement path.**

---

# 9. Browser/local security research

Localhost binding is a major boundary, but browser state changes still need an explicit auth/session/origin/CSRF model. CORS does not authenticate a request.

Rúnmál security design lives in `SECURITY_MODEL.md` and must be tested with negative cases.

Key derived rules:

- loopback by default;
- deliberate mode change for LAN/WAN bind;
- secrets referenced, redacted and excluded from portable exports;
- imported archives/assets are untrusted input;
- Python extensions are trusted code absent a real sandbox.

---

# 10. Testing facts that changed the roadmap

## 10.1 Pytest empty suite

Pytest documents exit code **5** for "no tests were collected." Therefore the original S101 phrase "pytest green on empty suite" was not a valid acceptance contract.

Primary docs: https://docs.pytest.org/en/stable/reference/exit-codes.html

**Roadmap correction:** S101 creates at least one real smoke test and requires pytest exit 0.

Status: **VERIFIED-DOC**.

## 10.2 Live provider tests

CI should not require paid OpenRouter credentials, Ollama running locally or physical audio hardware. Provider parsers use recorded/fake contract fixtures in ordinary CI; live tests are tagged separately.

This is a Rúnmál engineering decision, not a claim about an external project.

---

# 11. Backup and sovereignty research

SQLite provides a supported online backup API and transaction semantics suitable for safe local backup. Portable user-state export is a different problem from copying the database.

Primary backup docs: https://www.sqlite.org/backup.html

Rúnmál therefore distinguishes:

- installation backup;
- versioned portable `.runmal` archive;
- rebuildable derived indexes/vectors.

A release-level recovery test should restore old user state on a clean install and allow continued conversation, potentially under a different compatible provider/embedding profile.

See `BACKUP_AND_RECOVERY.md`.

---

# 12. License policy / taint watchlist

Rúnmál is Apache-2.0 and intends a permissive-only distributed dependency posture. This is a project policy stricter than simply asking whether combining two packages is legally possible.

Do not ship a dependency because a blog says its license is fine. Verify the exact version/artifact at release time.

Watch categories:

| Area | Risk | Action |
|---|---|---|
| SillyTavern source code | AGPL project; clean-room independence is core goal | Study public behavior/docs/specs, do not copy implementation |
| TTS runtimes | Wrapper/model/dependency licenses may differ | Full dependency/model/voice audit before acceptance |
| Character assets | Card/archive may contain independently licensed assets | Preserve attribution/metadata; do not imply Rúnmál relicenses imports |
| Model weights | Code license does not govern every weight file | Record model license in SBOM/manifest |
| Optional services | Network/service licenses can change distribution posture | Review exact deployed/distributed artifact |

Campaign VIII adds an SBOM + license gate so this policy is executable rather than prose.

---

# 13. Research verification ledger

Use this section as the fast list of facts that matter before coding.

| Claim/decision | State 2026-10-12 | Recheck owner |
|---|---|---|
| Current v3 archive is CHARX; normative spec outranks old concepts doc | VERIFIED-DOC | S113 |
| Ollama native embedding endpoint is `/api/embed` | VERIFIED-DOC | S304 |
| sqlite-vec is suitable enough to prototype behind an interface | CANDIDATE | S401 |
| faster-whisper small/int8 meets target hardware latency | UNVERIFIED RUNTIME | S503 |
| Kokoro full selected runtime is permissive-only | UNVERIFIED until dependency audit | S504 |
| Silero thresholds fit Volmarr's room/noise conditions | UNVERIFIED RUNTIME | S502 |
| ~2-second voice target is reachable on final pipeline | UNVERIFIED RUNTIME | S514 |
| OpenRouter exact current pricing/data-routing policy | REVERIFY when needed | S303 / user-facing docs |
| Aesir external API shape | PROJECT DEPENDENCY NOT FINAL | Campaign VII |

When an item becomes runtime-verified, record hardware, OS, dependency/model version and commit in a benchmark/ADR rather than simply changing the label to "verified."

---

# 14. Open research questions

1. Which exact CHARX/v3 compatibility fixtures can be legally committed for regression testing?
2. What browser authentication/session mechanism best fits local-first UI plus deliberate LAN exposure without adding needless complexity?
3. Which phonemization path gives Kokoro-quality English while satisfying the project's permissive-only distribution policy?
4. Does sqlite-vec remain the best embedded vector choice when Campaign IV begins, or has its API/stability picture changed?
5. Which embedding model becomes the default local memory profile, and what dimensions/storage footprint does it impose?
6. Should Prompt Trace be ephemeral by default or optionally persisted per generation for later debugging?
7. What exact Aesir HTTP contract will be stable enough for Campaign VII?
8. Which PC audio-capture strategy gives reliable VRChat room ingress while excluding the companion's own TTS output?
9. What release formats best serve Kubuntu/Linux and Windows without making containers mandatory?

Research answers should flow into the owning design document and roadmap slice, not remain stranded here.
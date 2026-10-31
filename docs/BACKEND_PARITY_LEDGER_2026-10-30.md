# P-008 — Backend Parity Ledger (2026-10-30)

*Which inference backends the mirrors speak that Rúnmál doesn't yet
(and vice versa), each judged wanted/unwanted with reasons. Mirror
input is P-002 rows ST-41–ST-45 and P-003 rows VX-15–VX-19 (public
docs and release notes only — clean-room law); Rúnmál's side is this
tree, read directly, with the proving file named per claim. This
ledger assigns nothing: wanted items with no home in the defined
parts are flagged for the Part I gate (P-014), exactly as P-004
flagged its NO-HOME rows.*

## Verdict vocabulary

- **HAVE** — an adapter exists in this tree today.
- **WANTED-GENERIC** — not present today; wanted; and the wanted
  build is *one* generic OpenAI-compatible adapter (see §3), not a
  bespoke adapter per brand.
- **WANTED-TEXT** — wanted as part of the later text-completion
  paradigm work (§4), not as a chat adapter.
- **UNWANTED** — judged not wanted, with the reason in the row.
  A bespoke adapter for the same endpoint may still be unwanted
  even where the endpoint itself is reachable another way; the
  row says which claim is being judged.
- **NOT-A-BACKEND** — a service shape the censuses mention beside
  backends; reassigned to its real home, not judged as a backend.

## 1. What Rúnmál actually has (from the tree)

Chat backends selectable in a backend profile
(`src/runmal/backends/profiles.py`: `CHAT_BACKENDS`):

| Backend | Adapter | Surface | Proving test |
|---|---|---|---|
| fake | `backends/fake.py` (`backend_key="fake"`) | in-process test double | `tests/test_s301_backends.py` (contract suite) |
| ollama | `backends/ollama.py` (`backend_key="ollama"`) | native `/api/chat` NDJSON | `tests/test_s302_ollama.py` |
| openrouter | `backends/openrouter.py` (`backend_key="openrouter"`) | OpenAI-compatible SSE at `openrouter.ai/api/v1` | `tests/test_s303_openrouter.py` |
| aesir | `backends/aesir.py` (`backend_key="aesir"`) | OpenAI-compatible surface at a profile-configured `base_url` | `tests/test_s701_aesir.py` |

Embedding backends, independent per profile (ADR-0001;
`EMBEDDING_BACKENDS`): `fake`, `ollama` (native `POST /api/embed`),
`aesir` (`POST /embeddings`), plus the `unavailable` backend whose
documented behaviour is the FTS fallback (`embed_or_fallback` —
a degraded result, never a crash; `backends/embeddings.py`,
`tests/test_s304_embeddings.py`, `tests/test_s703_aesir_embeddings.py`).

Two older seams name backends the profile layer does not:

- The connection-profile layer (S211, `connections/service.py`:
  `VALID_BACKENDS = ("fake", "ollama", "openai")`) names a generic
  **openai** kind — but there is *no* generic OpenAI chat adapter
  behind it in `backends/`: `build_chat_backend` knows only
  fake/ollama/openrouter/aesir. The name exists; the engine does
  not. This is the single most concrete gap in this ledger (§3).
- The sampler-compatibility layer (S208, `generation/compat.py`)
  has exactly two wire profiles, `openai` and `ollama` — sampler
  truth for any future generic adapter is already half-built.

Vice versa — what Rúnmál has that neither mirror names: **Aesir**
as a first-class sovereign backend (the founding road's whole
Campaign VII; no mirror speaks to Volmarr's own engine), a
**fake/contract backend** every adapter is proven against
(`backends/contract.py`), **per-modality profile composition**
(chat, embeddings, STT, TTS chosen independently per profile —
the shape Voxta's VX-15 service slots also reach for, judged
HAVE-THIN at P-004), and an **embeddings seam with an honest FTS
fallback** instead of a hard failure.

## 2. The mirror ledger (22 distinct named backends/sources)

Counted from the tables: SillyTavern names 13 Chat Completion
sources (ST-42) and 7 Text Completion backends (ST-43); Voxta
names 3 further distinct engines (VX-16). Ollama and llama.cpp
each appear under both mirrors/paradigms and are counted once.
**22 distinct named entries: 2 HAVE, 14 WANTED-GENERIC (two of
them also WANTED-TEXT), 6 UNWANTED.**

### Table A — SillyTavern Chat Completion sources (ST-42)

| Source | Verdict | Reason / route |
|---|---|---|
| OpenAI | WANTED-GENERIC | Direct access belongs under the generic adapter; many of its models are also reachable today via the OpenRouter adapter, which is a router, not a substitute for a direct profile. |
| Claude (Anthropic) | WANTED-GENERIC | No bespoke Anthropic adapter: direct access only insofar as a compatible surface is offered, otherwise via OpenRouter. A native adapter is re-opened only if a feature the generic surface cannot carry is proven needed. |
| Google AI Studio | WANTED-GENERIC | Same rule as Claude: generic surface or router, no bespoke adapter. |
| Google Vertex AI | UNWANTED (bespoke) | Enterprise cloud auth and project machinery are the opposite of this app's local-first shape; models reachable via router/generic routes need no Vertex adapter. |
| Mistral AI | WANTED-GENERIC | An OpenAI-shaped cloud source; a profile on the generic adapter, not new code per brand. |
| DeepSeek | WANTED-GENERIC | Same shape as Mistral. |
| AI21 | WANTED-GENERIC | Same shape; low priority (no founding-road demand recorded). |
| Cohere | WANTED-GENERIC | Same shape; low priority, as AI21. |
| Perplexity | WANTED-GENERIC | Same shape. |
| Fireworks AI | WANTED-GENERIC | Same shape. |
| Electron Hub | UNWANTED (bespoke) | A niche router; OpenRouter already fills the router slot. If its endpoint is OpenAI-compatible it works as a generic-adapter profile with no new code. |
| OpenRouter | HAVE | `backends/openrouter.py` (S303). |
| Custom (OpenAI-compatible) | WANTED-GENERIC | **The key gap.** The mirror's most-used escape hatch — any local or cloud endpoint that speaks the common shape, model list pulled from `/v1/models`. Rúnmál's connection layer already names this kind (`openai`, S211) but no chat adapter exists (§1). Highest-leverage single build in this ledger. |

### Table B — SillyTavern Text Completion backends (ST-43)

| Backend | Verdict | Reason / route |
|---|---|---|
| llama.cpp | WANTED-GENERIC + WANTED-TEXT | A local, sovereign engine both mirrors name (also VX-16). Its server belongs under the generic adapter for chat and under the text paradigm (§4) for completion; no bespoke adapter. |
| Text Generation WebUI (oobabooga) | WANTED-GENERIC + WANTED-TEXT | A local server wrapper, not an engine; covered by the generic adapter / text paradigm insofar as its public API offers the common shape. |
| TabbyAPI | WANTED-GENERIC | The API server that carries ExLlamaV3 (VX-16); covering TabbyAPI's shape covers that engine too. |
| KoboldCpp | WANTED-GENERIC | A local llama.cpp derivative with a public API; generic coverage, no bespoke adapter. |
| NovelAI | UNWANTED | A bespoke, proprietary, subscription text service with its own non-compatible API and a fiction-specific model line. No founding demand; re-open only on Volmarr's word. |
| Ollama | HAVE | Native adapter (S302) — the one text-list name Rúnmál already speaks natively. |
| AI Horde | UNWANTED | See §5 — this is the judgement P-004 explicitly reserved to this slice (ST-44). |

### Table C — Voxta engines (VX-16)

| Engine | Verdict | Reason / route |
|---|---|---|
| llama.cpp | (counted in Table B) | Both mirrors name it; one row, one verdict. |
| ExLlamaV3 | UNWANTED (direct) | An *engine library*, not a server API: it reaches users through TabbyAPI, which Table B already covers. A direct in-process binding would break Rúnmál's replaceable-engine contract (`docs/BACKEND_CONTRACT.md` §1). |
| Voxta Cloud | UNWANTED | Voxta's proprietary cloud/subscription tier. VX-01 is already DELIBERATELY-DIFFERENT at P-004 (no cloud/subscription tier; the sovereign replacement stands). Its routed/cloud providers are unnamed in the census and are covered, where OpenAI-shaped, by the generic verdict. |

## 3. The one build that covers most of the gap

Fourteen of the 22 entries are WANTED-GENERIC. They do not need
fourteen adapters; they need **one generic OpenAI-compatible chat
backend**: profile-configured `base_url` + secret reference +
`/chat/completions` SSE + `/v1/models` listing, passing the same
shared contract suite (`backends/contract.py`) every adapter
passes, with sampler truth declared per endpoint (the S208
`openai` compat profile already exists) and provider identity
kept inside the adapter (INV-001/002). The Aesir adapter is the
living proof this shape works in this tree — it *is* an
OpenAI-compatible adapter with a fixed name; the generic build
generalises it (configurable endpoint, no Aesir assumptions),
it does not start from zero. The same adapter's embeddings half
(`POST /embeddings`) answers the mirrors' "multiple embedding
sources" surface (ST-59 names no specific source in the census):
Rúnmál embeddings today are ollama/aesir/fake only.

**Road home: NO HOME in the defined parts.** Parts II–VI of the
filed roadmap contain no backend slice. This ledger therefore
flags the generic adapter — and every WANTED row that rides on
it — to the Part I gate (P-014) for assignment, exactly as P-004
flagged its NO-HOME rows. It is this ledger's first
recommendation to the gate, and to P-013's priority order: it is
small, it is the mirrors' widest surface, and the connection
layer already promises its name to users.

## 4. The paradigm gap (ST-41)

SillyTavern keeps two paradigms — Chat Completion (role messages)
and Text Completion (one assembled prompt string), each with its
own presets and templates. Rúnmál today is **chat-paradigm only**:
every adapter consumes `ChatMessage` lists. A text-completion
mode is **WANTED-TEXT, later**: it matters for the local-engine
crowd (llama.cpp/KoboldCpp completion endpoints) and for Part IV's
instruct/context templates (P-050/P-051), which are its natural
kin and partial home. No chat adapter in §2 is blocked on it.

## 5. AI Horde — the reserved judgement (ST-44)

**UNWANTED — deliberately.** SillyTavern offers AI Horde as a
free, shared, no-account inference pool: the zero-setup first
connection. Rúnmál does not build it, for three stated reasons:
(1) *privacy* — prompts are executed on strangers' volunteer
machines, which contradicts this app's custody story for the
user's own characters and chats; (2) *capability truth* — a
shifting volunteer pool cannot declare the sampler/capability
honesty this contract requires (BACKEND_CONTRACT §4–§5);
(3) *sovereignty of the default* — Rúnmál's zero-setup first
connection already exists and is local: the fake backend for
evaluation, Ollama for real local inference, Aesir as the
intended heart. Re-open only on Volmarr's explicit word; this
row is recorded as a judgement, not an oversight, and P-014
should carry it as DELIBERATELY-DIFFERENT for ST-44.

## 6. Not backends (reassigned, not judged)

- **Decisions (VX-17)** — a multiple-choice classification
  *service shape* (who speaks next, may a tool run), served in
  Voxta via its cloud, OpenRouter, or a local mode. Rúnmál's
  group-speaker policies (S211) and director seam (S212) are the
  local kin; any parity build belongs with scenarios/actions
  (Part IX territory), not in the backend registry.
- **Coding-agent backends (VX-55: Claude Code, OpenAI Codex)** —
  workspace agents, Part XI territory; they consume inference,
  they are not inference backends.
- **STT/TTS services (VX-14, ST-62/ST-63)** — P-010's voice
  provider census owns them; this ledger is chat/embedding only.
- **Per-source secrets (ST-45)** — already HAVE, and not a
  backend: profile secret references, server-side only (S306,
  INV-023).

## 7. Summary for the gate (P-014) and priority (P-013)

1. **One wanted build covers 14 of 22 mirror entries**: the
   generic OpenAI-compatible chat (+embeddings) adapter. NO HOME
   in Parts II–VI — P-014 must assign it or drop it knowingly.
2. **Text-completion paradigm**: WANTED-TEXT, kin home Part IV;
   P-014 confirms.
3. **Six UNWANTED verdicts with reasons**: Vertex AI (bespoke),
   Electron Hub (bespoke), NovelAI, AI Horde (§5), ExLlamaV3
   (direct), Voxta Cloud. None is an oversight; each re-opens
   only on Volmarr's word or the stated condition in its row.
4. **Vice versa stands**: Aesir, the contract/fake backend,
   per-modality profiles, and the FTS-degrading embeddings seam
   are Rúnmál-only strengths the mirrors do not name; parity
   work must not trade them away for breadth.

## 8. F-01 follow-on (2026-10-30) — the generic adapter is built

The P-014 gate homed this ledger's first recommendation as
follow-on **F-01**, and F-01 is now banked: the generic
OpenAI-compatible adapter exists in this tree
(`backends/openai_compat.py`, `backend_key="openai"`, chat plus
embeddings in `backends/embeddings.py`), is selectable in backend
profiles (`CHAT_BACKENDS` / `EMBEDDING_BACKENDS` both gained
`openai`), passes the shared contract suite against fixtures, and
declares exactly the S208 `openai` sampler profile as its truth.
The 14 WANTED-GENERIC rows in Tables A–C are therefore covered as
*profiles on this one adapter* wherever the named service offers
the compatible surface — the ledger's original verdicts above are
the historical record of the gap and are not rewritten; this note
is the gap's closing entry. The six UNWANTED verdicts stand
unchanged. Full record: `docs/GENERIC_OPENAI_ADAPTER_2026-10-30.md`.
